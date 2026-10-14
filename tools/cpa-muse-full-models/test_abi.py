"""Exercise the public native ABI, including allocated response ownership."""
import ctypes as c
import json
import pathlib
import subprocess
import tempfile
import unittest


class Buffer(c.Structure):
    _fields_ = [("ptr", c.c_void_p), ("len", c.c_size_t)]


Call = c.CFUNCTYPE(c.c_int, c.c_char_p, c.c_void_p, c.c_size_t, c.POINTER(Buffer))
Free = c.CFUNCTYPE(None, c.c_void_p, c.c_size_t)
Shutdown = c.CFUNCTYPE(None)


class Plugin(c.Structure):
    _fields_ = [("abi_version", c.c_uint32), ("call", Call),
                ("free_buffer", Free), ("shutdown", Shutdown)]


class NativeABI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = pathlib.Path(__file__).resolve().parent
        subprocess.run(["sh", str(root / "build.sh"), cls.temp.name],
                       check=True, capture_output=True)
        cls.library = c.CDLL(str(pathlib.Path(cls.temp.name) / "cpa-muse-full-models.so"))
        cls.library.cliproxy_plugin_init.argtypes = [c.c_void_p, c.POINTER(Plugin)]
        cls.library.cliproxy_plugin_init.restype = c.c_int

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.api = Plugin()
        self.assertEqual(self.library.cliproxy_plugin_init(None, c.byref(self.api)), 0)
        self.assertEqual(self.api.abi_version, 1)

    def request(self, method):
        out = Buffer()
        self.assertEqual(self.api.call(method, None, 0, c.byref(out)), 0)
        self.assertTrue(out.ptr)
        try:
            return json.loads(c.string_at(out.ptr, out.len))
        finally:
            self.api.free_buffer(out.ptr, out.len)

    def test_lifecycle_keeps_registration_stable(self):
        initial = self.request(b"plugin.register")
        self.assertEqual(initial, self.request(b"plugin.reconfigure"))
        self.assertTrue(initial["ok"])
        # The real host rejects registration if any required metadata is empty.
        metadata = initial["result"]["metadata"]
        for field in ("Name", "Version", "Author", "GitHubRepository"):
            self.assertTrue(metadata.get(field, "").strip(), field)
        registry = json.loads((pathlib.Path(__file__).parent / "registry.json").read_text())
        self.assertEqual(initial["result"]["metadata"]["Version"], registry["plugins"][0]["version"])
        # Registrar metadata is additive. ModelProvider would replace OAuth discovery.
        self.assertEqual(initial["result"]["capabilities"], {"model_registrar": True})

    def test_registration_routes_exact_full_ids_to_builtin_meta(self):
        result = self.request(b"model.register")["result"]
        self.assertEqual(result["Provider"], "meta")
        self.assertEqual({m["ID"] for m in result["Models"]},
                         {"muse-wonder-full-1.0", "muse-wonder-full-1.0-contributor"})
        self.assertTrue(all(m["ID"] == m["Name"] and m["Type"] == "meta"
                            for m in result["Models"]))

    def test_repeated_calls_own_independent_buffers(self):
        first, second = Buffer(), Buffer()
        self.assertEqual(self.api.call(b"model.register", None, 0, c.byref(first)), 0)
        self.assertEqual(self.api.call(b"model.register", None, 0, c.byref(second)), 0)
        try:
            self.assertNotEqual(first.ptr, second.ptr)
            snapshot = c.string_at(second.ptr, second.len)
            self.api.free_buffer(first.ptr, first.len)
            first.ptr = None
            self.assertEqual(snapshot, c.string_at(second.ptr, second.len))
        finally:
            self.api.free_buffer(first.ptr, first.len)
            self.api.free_buffer(second.ptr, second.len)
        for _ in range(100):
            self.assertTrue(self.request(b"model.register")["ok"])

    def test_invalid_calls_fail_without_breaking_later_registration(self):
        self.assertNotEqual(self.library.cliproxy_plugin_init(None, None), 0)
        self.assertNotEqual(self.api.call(b"plugin.register", None, 0, None), 0)
        for method in [None, b"not-a-method"]:
            self.assertFalse(self.request(method)["ok"])
        self.assertTrue(self.request(b"plugin.register")["ok"])


if __name__ == "__main__":
    unittest.main()
