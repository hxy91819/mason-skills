---
name: tencent-cloud-pitfalls
description: 腾讯云开通与排障的已知坑。两种情况使用：在新主账号上首次用 IaC 或 API 开通产品（TKE 网络插件、CLS 采集、云监控告警、COS 策略、TCR、CLB、DNSPod、TAT）；或腾讯云 API 返回不说明原因的拒绝，如 ClusterNotSuitEnableVPCCNI、role not exist、TradeFailed、NotPurchased、ServiceNotSubscribed。只选择 tccli 账号或查询已有资源时不使用。
---

# 腾讯云开通与排障踩坑

这些经验来自一个平台项目：2026-11 在一个全新的生产主账号上开通 TKE、数据库、日志、监控和镜像仓库。

同样的参数在老账号上能成功，在新账号上却被拒，而且报错不提缺什么。花时间最多的几次：

| 问题 | 耗时 |
| --- | --- |
| VPC-CNI 开启被拒 | 约 23.5 小时、10 个 MR |
| 云监控原生告警不触发 | 约 1.5 天 |
| CLS 采集组件逐个暴露缺权限 | 约 1 天、十余个 MR |
| TCR 首次创建 | 约 20 小时 |

## 新账号：先对齐账号层，再开通产品

先拿一个跑通过同类产品的老账号做参照，逐项对比下面三类，再开始写产品资源。

1. **服务角色。** 用 `tccli cam DescribeRoleList` 列出两个账号的角色，按角色名对比。新账号缺的角色，用 `GetRole` 和 `ListAttachedRolePolicies` 从老账号抄下信任主体和预设策略，再用 IaC 建：只信任官方 service 主体，只挂预设策略。
2. **服务开通。** SSM、CFS、Private DNS 这类要单独开通的服务，做成一个一次性的登记入口，不要在产品资源里顺手开通。
3. **控制台授权。** 有些授权只能由账号负责人在控制台同意，例如 TCR 首次创建。开工前把这类授权列出来交给负责人。

**完成判据：** 计划用到的每个产品都标了三种结论之一：角色已建、服务已开通、确认不需要。

一个新账号实际缺过的，可作对照起点（不是全集）：

- `_QCSRole` 结尾的服务角色：CloudAudit、TKE、AS、TCR、IPAMDofTKE；
- 两个 `CM_QCSLinkedRole*`：InQueryInstance、InCloudResources；
- 三项服务开通：SSM、CFS、Private DNS。

## API 拒绝又不说明原因时

- **先查账号级前提**：角色、服务开通、白名单、配额。资源属性逐项对比都一致时，差异多半在账号层，地域和参数可以放到后面查。
- **每次只改一个变量**：用 0 节点的临时集群，一次只改一个字段，同时保留一个对照（换个地域，或换个账号）。最后在同一个对象上只补上候选的前提，看结果是否翻转；翻转了才算确认根因。
- **工单只问一件事**：请厂商诊断一个具体的 RequestId，并写明不需要代为操作。
- **结果不明的写请求不重发**，尤其是采购类。先回读订单或资源，确认没成功再发。
- **CAM 改动有传播延迟**，刚补完授权立刻失败的，隔一会儿再试一次。

## 按产品查

开通或修改某个产品之前，先读 [references/product-pitfalls.md](references/product-pitfalls.md) 里对应的一节。涵盖：

- TKE 网络与 DNS
- CLS 采集
- 云监控
- COS
- TAT
- 自定义镜像
- CLB
- TCR
- DNSPod
- 删除顺序
- 单账号多业务时的 CAM
- 配额与账单
- 零散的参数问题

用临时管理员密钥操作生产账号，或在多人共用的账号里操作时，先读 [references/production-operations.md](references/production-operations.md)。
