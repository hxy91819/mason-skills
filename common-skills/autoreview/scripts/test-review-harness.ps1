[CmdletBinding()]
param(
    [ValidateSet('malicious', 'benign')]
    [string] $Fixture,

    [ValidateSet('codex', 'claude', 'pi', 'bb')]
    [string[]] $Engine,

    [string[]] $ExternalReviewDestination,

    [Alias('h')]
    [switch] $Help
)

$ErrorActionPreference = 'Stop'

$Harness = Join-Path $PSScriptRoot 'test-review-harness.py'
$ForwardedArgs = @()

if ($Help) {
    $ForwardedArgs += '--help'
}

if ($PSBoundParameters.ContainsKey('Fixture')) {
    $ForwardedArgs += @('--fixture', $Fixture)
}

if ($PSBoundParameters.ContainsKey('Engine')) {
    foreach ($SelectedEngine in $Engine) {
        $ForwardedArgs += @('--engine', $SelectedEngine)
    }
}

if ($PSBoundParameters.ContainsKey('ExternalReviewDestination')) {
    foreach ($Destination in $ExternalReviewDestination) {
        $ForwardedArgs += @('--external-review-destination', $Destination)
    }
}

$PyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($null -ne $PyLauncher) {
    & $PyLauncher.Source -3 $Harness @ForwardedArgs
    exit $LASTEXITCODE
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if ($null -ne $Python) {
    & $Python.Source $Harness @ForwardedArgs
    exit $LASTEXITCODE
}

Write-Error 'Python 3 is required to run test-review-harness.'
exit 127
