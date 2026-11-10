# 按产品的踩坑

每节先写现象，再写做法。报错码照原文保留，方便搜索。

## TKE 网络（VPC-CNI 与 GlobalRouter）

- **开启 VPC-CNI 报 `UnsupportedOperation.ClusterNotSuitEnableVPCCNI`。** 集群属性和能成功的账号逐项相同，原因是账号缺服务角色 `IPAMDofTKE_QCSRole`。补法：建这个角色，只信任 TKE 服务主体，挂预设策略 `QcloudAccessForIPAMDofTKERole`。补完后，原请求单次重试就成功了。
- **GlobalRouter 的容器网段必须在 VPC 网段之外。** 写在 VPC 网段里会报 `CidrConflictWithVpcCidr`。
- **删掉集群后，网段要等一会儿才能复用。** 立即复用会报 `CidrConflictWithOtherCluster`，等约 10 分钟。各地域、各对端的网段要统一登记并查重。
- **`onlyNominatedEniSubnets` 对已挂 ENI 的节点不生效。** 它用来限定 ENI 从哪些子网分配地址。要让某个子网专供一类 Pod，还得加准入策略，禁止其他 Pod 申请该子网；安全组也只放行这个子网。
- **改网络插件配置（`UpdateAddon`）先用 DryRun 跑一遍。**

## TKE 里的 DNS

- **Pod 内第一次 DNS 解析要约 10 秒。** 改用 TCP DNS，并把 `ndots` 设为 1。
- **新 Pod 已经 Ready，DNS 可能还要约 20 秒才通。** 把 DNS 可解析写进 readiness 检查，否则发布时会出现偶发失败。

## TKE kubeconfig

- **`DescribeClusterKubeconfig` 返回 200，只说明发到了调用者自己的证书。** 核对证书的 CN 和 O，对敏感 RBAC 发一次应该被拒绝的请求，并确认管理员接口 `DescribeClusterSecurity` 被 CAM 拒绝。不要把接口成功当成已经拿到管理员权限。

## TKE 节点池与包月退还

- **`DescribeClusterNodePools` 的 `TotalCount` 不是过滤后的条数。** 接口版本 2018-05-25。用 `Filters` 的 `NodePoolsId` 过滤后，`NodePoolSet` 可以是空的，`TotalCount` 仍是集群里的池子总数。精确删除的终态看过滤后的集合，不能要求 `TotalCount=0`。
- **`DeleteClusterInstances` 的 `InstanceDeleteMode=terminate` 只适用于按量。** 官方参数：terminate 销毁实例，且仅支持按量；retain 只移出集群、保留实例。包月节点不要走 terminate。见 [删除集群中的节点](https://cloud.tencent.com/document/product/457/31864)。
- **包月节点先移出池，再退还 CVM。** `DeleteClusterNodePool` 的 `KeepInstance=true` 会删掉节点池，节点移出集群，对应实例不退还。池还在、且伸缩组 min 等于 desired 时，先退还会被伸缩组补回。先确认原池和伸缩组都没了，再逐台退还。这一顺序已在包月节点上实测：池和伸缩组消失，CVM 仍在，随后第一次 `TerminateInstances` 进入回收站。
- **包月 `TerminateInstances` 第一次是进回收站，第二次才不可恢复销毁**（CVM 2017-03-12）。按量在该接口说明里是直接销毁；[销毁概述](https://cloud.tencent.com/document/product/213/4930)又写按量手动销毁最多在回收站留 2 小时。两份文档不一致时，按这次计费类型的实际回读验收，不套用另一类。包月第一次主动退还的终态是 `SHUTDOWN` 且 `IsolatedSource=MANMADE`，系统盘进入回收状态，再对退费订单；不要用“实例已经不存在”当这一次的成功标准，也不要重放同一次请求去追求不存在。永久销毁是另一次新请求。包月进回收站后概述页写最多保留 15 天，天数以现行文档为准。见 [TerminateInstances](https://cloud.tencent.com/document/api/213/15723)。

## CLS 日志采集（TKE 集成）

- **采集组件的权限是一个一个暴露出来的。** 现象是组件反复重启，每补一个权限就露出下一个，依次是 `ModifyTopic`、`DescribeMachineGroups`、`CreateMachineGroup`、`ModifyMachineGroup`、`CreateConfig`、`ApplyConfigToMachineGroup`、`ModifyConfig`。原因是组件用的是 `TKE_QCSRole`，它的预设策略只带旧的 CLS 动作。做法：照官方动作表一次把权限列全，并限定到精确资源，不要授权 `cls:*`。
- **LogConfig 缺 `logsetName` 会一直停在 Stale。**
- **机器组要用 TKE 标签方式**：`Flag=label_tke`，同时带上 `ClusterId` 和 `ClusterRegion`。
- **声明、原生绑定和真实日志是三件事。** LogConfig 已 Synced、原生配置和机器组已绑定、目标容器的 stdout 真的到达，要分开核对。其中一层返回成功，不能给整条链路签收。
- **看组件日志只看最新的几十行。** 尾部截取太长时，最新的那条报错会被截断。

## 云监控与告警

- **补齐两个 `CM_QCSLinkedRole*` 之后，数据库的原生阈值告警仍然不出事件。** 当时把阈值压到 0.01%，演练了 10 分钟和 16 分钟两轮，告警历史始终为空，根因至今不明。做法：原生告警必须用压低阈值的演练真打出一次事件，才算接通；打不出来就尽早改走官方 exporter → Prometheus → 通知渠道。
- API 细节：
  - 数据库类告警的 `ProjectId` 传 `-1`；
  - `CreateAlarmPolicy` 的 Filter 会被忽略，要另调 `BindingPolicyObject` 绑定对象；
  - `insttype` 用 `master`/`ro`，不是 `rw`；
  - 告警策略和 `GetMonitorData` 用的命名空间不同；
  - `ModifyAlarmPolicyCondition` 里传 `Enable` 不生效，启停要用 `ModifyAlarmPolicyStatus`；
  - CynosDB `DescribeInstances` 实际要 `instance/*` 级的资源授权，和 CAM 文档写的集群级不一致。精确实例 ID 也一样。留下真实拒绝，只采集已登记的 ID，不要为了能枚举而扩大库存读权限；别的产品能按资源授权，不要套过来。
- **策略保存成功，仍要单独核绑定。** 回读不带过滤条件的绑定列表、`IsBindAll` 和数量。数据库核对 appid、clusterid、instanceid、insttype 四项都在；缺一项就不算绑到目标。CM 服务角色缺失，和“规则在但没有事件”不是同一件事。
- **只读监控身份**：`GetMonitorData`、`DescribeBaseMetrics` 和各产品的 `DescribeInstances` 有的不支持资源级授权，只能授权到 `*`。授权时只给读动作。

## COS

- **条件键 `cos:prefix` 的值要 URL 编码**，`/` 写成 `%2F`。不编码时，策略回读看起来正常，按前缀列举却一直 403。
- **回读策略时比较原始 JSON。** 回读工具如果把 `%2F` 解码回去，会报出假的不一致。
- **改完策略，用真实请求分别验证放行和拒绝两种情况。**

## TAT（自动化助手）

- **agent 版本下限按功能需要和官方发布定，不要照抄其他地域的实测值。** 某个地域的官方安装包就是比另一个地域旧一个小版本，照抄过来的下限会让制镜卡住。
- **CVM 已经 Running，TAT 可能还没 Online**，此时调用报 `AgentStatusNotOnline`。Online 状态和版本要在同一次回读里判断；下发命令前先等它上线。
- **不要钉 agent 二进制的摘要。** 云厂商会在机器首次启动时改写或升级它，钉了摘要检查就会变脆。准入只看四项：安装路径、进程在运行、云侧显示 Online、版本不低于下限。
- 查执行结果要 `tat:DescribeInvocations` 权限。把代码里实际调用的云 API 动作和授予的权限做覆盖比对，缺的在 CI 里报出来。
- 官方文档说明 agent 升级不需要 `TAT_QCSLinkedRole*`，新账号没有这两个角色不必补。

## 自定义镜像

- **捕获镜像前清除机器身份**：删除 SSH 主机密钥，清空 machine-id，让每台克隆在首次启动时重新生成。捕获后自动审计一遍。
- 验收方法：用一台种子机加两台独立克隆，各重启几轮，确认身份互不相同、服务都能起来。

## CLB

- **有的账号不能指定可用区。** 出现过三种拒绝：传数字区号被拒；传 `ZoneId` 报 "don't support specify parameter ZoneId"；只传 `MasterZoneId` 报不支持容灾 CLB。这时 `DescribeResources` 却显示可售。最后不指定可用区，分配到的是没有 VIP 的域名型实例。
- 做法：设计双可用区网络之前，先用一次真实创建验证这个账号能拿到什么。"可售"不等于账号有这个能力。参数被拒就留下那次回执，改为不传可用区，让服务分配后再回读主区和备区。域名型实例的 VIP 可以为空；空 VIP 不等于未就绪，以原生状态为准。

## TCR（镜像仓库）

- 首次创建报 `TradeFailed`，由账号负责人在控制台同意授权后通过。记录里没能证明它和服务角色有关。
- 之后还会接连碰到：
  - 要先开公网 endpoint，才能查白名单；
  - 私网解析服务没开通，报 `ServiceNotSubscribed`；
  - provider 写完后 DNS 仍是 DISABLED，要先 refresh。
- **Bearer 请求的 403 可能是 CSRF，不是权限。** 取 token 的 GET 会留下会话 Cookie，后面的 OCI POST 会触发仓库的 CSRF。Bearer 调用前后清空 Cookie，再用新 tag 验证推送。不要为此扩大服务账号权限。
- 做法：创建前核对 TCR 服务角色、COS 授权和 Private DNS 是否已开通。`TradeFailed` 本身没有被证明就是缺角色。照 provider 源码里的调用顺序做；结果不明的采购只对账，不重发。同一连接失败后，先开通缺的服务再 refresh，不要删掉连接去建第二份 state。

## DNSPod

- **子域的解析区要建在父域所在的账号。** 在别的账号建会报 `InvalidParameter.QuhuiTxtRecordWait`。
- **`TransferSubDomain` 默认为 true，会把父域已有的子域记录迁走。** 显式设成 false，只委派真正需要的子域，例如 ACME 验证用的那个。
- **购买接口报 `UnknowError`，实际可能已经扣款**，而且不一定享受官网活动价。用稳定的 ClientToken。失败后按订单、套餐、域名三方对账，不要再买一次；活动网页价不能代替 API 实付。付款成功后还要 enable。权威返回 SOA REFUSED 是未启用，不是传播延迟。

## 删除回读

- **按依赖倒序删，确认子资源真的消失后再删父资源。** 先删了父网络，集群会卡在 Creating，普通删除和保留删除都报 `ResourceUnavailable.ClusterState`，只能提工单处理。
- `DeleteVpc` 要等关联资源异步释放完。
- **同一个“不存在”在不同 API 上长得不一样。** VPC `DescribeSecurityGroups`（2017-03-12）对已删除的精确 ID 返回 `ResourceNotFound`，不是 `TotalCount=0`。已经确认删除成功的请求不要重放。权限拒绝和参数错误也不能当成不存在。每个删除动作单独写明终态是空列表、明确的 NotFound，还是异步任务完成。不要把这一次的读回形状套到没有核过的 API。

## 单账号放多个业务时的 CAM

- **按标签限制的授权（`request_tag`）拦不住跨业务引用父资源。** 出现过的情况：
  - 被授权方能建子网、CLB、数据库，却能引用别的业务的 VPC；
  - 伸缩组的内层调用被拒；
  - `ModifyResourceTags` 能删掉业务标签。
- 做法：VPC、子网这类基础资源由管理员在账号层预建，再精确导入 IaC；业务角色只在预建的资源里创建实例。
- 按标签授权的写法：新建资源用请求标签做条件，存量资源用资源标签做条件。上线前实测四种情况：标签正确的放行；无标签、错标签、跨业务的三种都拒绝。不支持标签条件的接口单独处理，不能因为加不了条件就整体放开。

## 配额与账单

- **配额接口只能查到 CVM 台数**，查不到 vCPU、CBS、快照的上限。先按需求算用量，再和默认值对照。
- **普通公网 IP 每天只能分配 10 个**，和 EIP 配额是两回事。
- **订单里的 `ZoneCode` 是模板值**，地域以资源回读为准。
- **0 元订单不等于免费。** 还不知道的费用记成"未知"，不要记成 0。

## 零散的参数问题

- `CreateVpc` 的 `EnableMulticast` 要传字符串，SDK 往返测试测不出来。
- 入站和出站安全组规则放在同一个请求里会报 `Coexist`。
- 安全组回读时，协议和端口的大小写和请求时不同，比较前先规范化。
- IaC provider 默认会读到中文的角色描述，preview 因此出现假的 update；描述和线上值对齐即可，不要用 ignoreChanges 掩盖。
- 节点密码只能 8–16 位。CynosDB 备份窗口的单位见下面 CynosDB 一节，不是整点小时数。
- `CreateAccessKey` 返回的字段名和常见写法不同，而密钥只在创建时可见，读取代码要先用测试验证。
- DryRun 通过不代表能真正下单，下单还要 `finance:trade` 权限。
- Ubuntu 24.04 镜像不能用在 S2 机型上。
- **中国大陆的域名要先备案。** 未备案的域名不论用什么端口、HTTP 还是 HTTPS，访问都会被拦截。控制台显示"正常"只代表注册和实名已完成，是否备案要另用备案状态接口查。

## CAM 写请求的类型

- **`DeletePolicy` 的 `PolicyId` 虽是单数，类型却是整数数组**（CAM 2019-01-16，参数名 `PolicyId.N`）。标量会被拒绝：审计里业务码 `apiErrorCode=207` / `InvalidParameter`，策略还在。字段名不能推断类型，写之前对照原生模型。见 [删除策略](https://cloud.tencent.com/document/product/598/34577)。
- **CloudAudit 外层 `errorCode=0` 只说明权限校验事件，不是业务写入成功。** 同时看业务 `apiErrorCode` 和资源终态。参数被明确拒绝的那次不要原样重放；改对类型后作为新请求。生产账号上的批准方式见 [production-operations.md](production-operations.md)。

## CynosDB

- **快照和逻辑备份窗口都是从午夜起的秒数。** 02:00–06:00 写 7200–21600。provider 示例里的小时数 2/6 和创建接口不一致，以服务端回读为准。
- **`DescribeClusters`（2019-01-07）没有 `ClusterIds` 参数。** 文档上的过滤是 `DbType` 加 `Filters`。传 `ClusterIds` 会被拒绝（实测 `UnknownParameter`）。类型化 SDK 可能在解析时丢掉未知字段，离线解析成功不能证明参数有效；以原生请求的接受或拒绝为准。见 [查询集群列表](https://cloud.tencent.com/document/api/1003/48085)。
- **`FlowId` / `TaskId` 只代表受理。** 失败的任务也有编号。终态看任务结果和资源回读。其他产品的任务号先当成只是受理，用该产品自己的终态查询核对，不要用这一次的字段名套过去。
- **`AddInstances` 会自己建 `singleRo` 端点。** 端点已经在，就只回读，不要再发一次创建。

## pulumi-tencentcloud v0.2.3

以下只对这个 provider 版本核过，不要套到其他版本或其他云的 provider。

- **`NewProvider` 会把进程里的密钥写进 provider 输入。** 标成 secret 也仍在加密 checkpoint 里。做法：注册相同类型、版本和地域，让插件继承环境认证；用真实 `CheckConfig` 核对，并扫描 checkpoint，确认没有密钥字段。
- **刷新已删除的节点池，不按 not-found 移出 state。** 报 `FailedOperation.NodePoolQueryFailed`，内层 `E501001` / `DBRecordNotFound`。不要无限重试 refresh，也不要笼统忽略这类错误。先用原生接口确认池和伸缩组都不存在，再只从 state 去掉这些已经不存在的 URN 和它们的直接依赖，其余 ID 不动。preview 和预期不一致就不要 up。state 里还有已删池时不要 up。
- **NORMAL 规格即使带了 `InstanceInitInfos`，仍要顶层 CPU 和内存。** 按原规格补上，不要改资源数量。
- **数据库账号 Create 可以原生成功，provider 却返回 nil state。** 停下来用原生接口核对账号已经在，不要当成没建成再创建。同一集群的账号和授权要串行，并发会 `TaskConflict`。Read 不返回密码，普通 import 可能计划改密。要纳管时只把原来的密码按原加密方式补进 state；preview 出现改密、替换或删除就停下。
- **数值写法和集合顺序会造成等价 diff。** `1` 和 `1.000000`、权限列表顺序不同，比较实际数值和集合，不要为抹平显示再 up。
