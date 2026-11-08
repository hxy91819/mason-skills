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

## CLS 日志采集（TKE 集成）

- **采集组件的权限是一个一个暴露出来的。** 现象是组件反复重启，每补一个权限就露出下一个，依次是 `ModifyTopic`、`DescribeMachineGroups`、`CreateMachineGroup`、`ModifyMachineGroup`、`CreateConfig`、`ApplyConfigToMachineGroup`、`ModifyConfig`。原因是组件用的是 `TKE_QCSRole`，它的预设策略只带旧的 CLS 动作。做法：照官方动作表一次把权限列全，并限定到精确资源，不要授权 `cls:*`。
- **LogConfig 缺 `logsetName` 会一直停在 Stale。**
- **机器组要用 TKE 标签方式**：`Flag=label_tke`，同时带上 `ClusterId` 和 `ClusterRegion`。
- **看组件日志只看最新的几十行。** 尾部截取太长时，最新的那条报错会被截断。

## 云监控与告警

- **补齐两个 `CM_QCSLinkedRole*` 之后，数据库的原生阈值告警仍然不出事件。** 当时把阈值压到 0.01%，演练了 10 分钟和 16 分钟两轮，告警历史始终为空，根因至今不明。做法：原生告警必须用压低阈值的演练真打出一次事件，才算接通；打不出来就尽早改走官方 exporter → Prometheus → 通知渠道。
- API 细节：
  - 数据库类告警的 `ProjectId` 传 `-1`；
  - `CreateAlarmPolicy` 的 Filter 会被忽略，要另调 `BindingPolicyObject` 绑定对象；
  - `insttype` 用 `master`/`ro`，不是 `rw`；
  - 告警策略和 `GetMonitorData` 用的命名空间不同；
  - `ModifyAlarmPolicyCondition` 里传 `Enable` 不生效，启停要用 `ModifyAlarmPolicyStatus`；
  - CynosDB `DescribeInstances` 实际要 `instance/*` 级的资源授权，和 CAM 文档写的集群级不一致。
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
- 做法：设计双可用区网络之前，先用一次真实创建验证这个账号能拿到什么。"可售"不等于账号有这个能力。

## TCR（镜像仓库）

- 首次创建报 `TradeFailed`，由账号负责人在控制台同意授权后通过。记录里没能证明它和服务角色有关。
- 之后还会接连碰到：
  - 要先开公网 endpoint，才能查白名单；
  - 私网解析服务没开通，报 `ServiceNotSubscribed`；
  - provider 写完后 DNS 仍是 DISABLED，要先 refresh。
- 做法：照 provider 源码里的调用顺序做；结果不明的采购请求不要重发。

## DNSPod

- **子域的解析区要建在父域所在的账号。** 在别的账号建会报 `InvalidParameter.QuhuiTxtRecordWait`。
- **`TransferSubDomain` 默认为 true，会把父域已有的子域记录迁走。** 显式设成 false，只委派真正需要的子域，例如 ACME 验证用的那个。
- **购买接口报 `UnknowError`，实际可能已经扣款**，而且不一定享受官网活动价。买没买成，以订单回读为准。

## 删除顺序

- **按依赖倒序删，确认子资源真的消失后再删父资源。** 先删了父网络，集群会卡在 Creating，普通删除和保留删除都报 `ResourceUnavailable.ClusterState`，只能提工单处理。
- `DeleteVpc` 要等关联资源异步释放完。

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
- 节点密码只能 8–16 位；CynosDB 的备份窗口必须是整点。
- `CreateAccessKey` 返回的字段名和常见写法不同，而密钥只在创建时可见，读取代码要先用测试验证。
- DryRun 通过不代表能真正下单，下单还要 `finance:trade` 权限。
- Ubuntu 24.04 镜像不能用在 S2 机型上。
- **中国大陆的域名要先备案。** 未备案的域名不论用什么端口、HTTP 还是 HTTPS，访问都会被拦截。控制台显示"正常"只代表注册和实名已完成，是否备案要另用备案状态接口查。
