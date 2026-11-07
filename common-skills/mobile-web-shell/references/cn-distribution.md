# 面向中国大陆发布移动 Web：渠道与登录门槛

核查日：2026-11-07。适用场景：个人或小团队、主机在境外、无 ICP 备案、应用含 LLM 对话，准备通过 H5、微信小程序或 iOS App 对外提供。

本文只列事实和证据，不替项目选择发布路线。网站 ICP 备案、小程序备案、App 备案、算法备案、生成式 AI 服务备案/登记、平台类目审核是不同层面，不能互相替代。

## 证据口径

- **官方明文**：主管机关或服务商自己的文本直接写明。
- **官方间接**：由官方文本推导，保留条件。
- **未证实**：没有取得足够官方证据，不等于允许。
- 页面没有发布日期时写“未标；查阅 2026-11-07”，不拿查阅日冒充发布日期。
- 云厂商帮助中心只能证明该厂商的服务规则，不能一概推广为全国法律。

## 1. 面向境内公众的生成式 AI 服务

### 1.1 适用范围

《生成式人工智能服务管理暂行办法》第二条以“利用生成式人工智能技术向中华人民共和国境内公众提供服务”为适用条件，没有按 H5、原生 App 或小程序排除；第二十二条的提供者包括组织、个人以及通过 API 提供服务者；第二十条专门规定境外向境内提供服务的处置。个人主体、境外主机、调用第三方模型都不是条文中的自动豁免条件。

来源：[国家网信办《生成式人工智能服务管理暂行办法》](https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm)，第二、二十、二十二条。2023-07-13 发布，2023-08-15 施行。

置信度：适用范围与提供者定义为官方明文；把条文应用到“个人 + 境外主机 + H5”组合为官方间接。

### 1.2 内容、用户和个人信息义务

提供者须承担内容生产者与网络信息安全责任；与注册用户签订服务协议；公开适用人群、场合、用途并采取防沉迷措施；保护输入与使用记录，不收集非必要个人信息；处置违法内容和违法使用；建立投诉举报入口。第十七条要求**具有舆论属性或者社会动员能力**的服务开展安全评估并履行算法备案；不能把限定条件删掉说成“任意 AI 功能都必须同一种大模型备案”，也不能把模型供应商备案当作应用所有义务已完成。

来源：同上，第四、九至十五、十七、二十三条。置信度：官方明文；具体应用是否具有舆论属性或社会动员能力、应办哪一种备案/登记，未证实。

### 1.3 AI 生成内容标识

2025 年《人工智能生成合成内容标识办法》已生效，涵盖文本。第四条对属于深度合成规定第十七条第一款情形的服务要求显式标识，文本可在文字或交互界面显著提示；第五条规定文件元数据隐式标识；下载、复制、导出亦有标识要求。第七条要求应用分发平台核验 AI 服务的标识材料。不能只援引 2023 年暂行办法“图片、视频等”的简述，推导聊天文本不需要标识。

来源：[《人工智能生成合成内容标识办法》](https://www.cac.gov.cn/2025-03/14/c_1743654684782215.htm)，第二至八、十二、十四条。2025-03-07 印发，2025-03-14 公布，2025-09-01 施行。置信度：官方明文；具体输出载体的实现要求仍需按适用标准判断。

### 1.4 邀请制体验是否豁免

第二条明确“未向境内公众提供”的研发、应用活动不适用；但条文没有列出“邀请制”“免费”“少于某人数”“测试版”自动豁免或人数阈值。仅凭邀请制和小规模，无法确认体验不面向公众。真正仅内部研发使用，与向外部用户发邀请码不能直接等同。

来源：暂行办法第二条。置信度：非公众例外及条文未列人数条件为官方明文；邀请制体验是否豁免未证实。

### 1.5 深度合成中的文本对话、实名与信息发布

《互联网信息服务深度合成管理规定》第二十三条明确包括问答对话等文本技术；第九条要求依法对使用者进行真实身份信息认证，列举移动电话号码、身份证件号码、统一社会信用代码、国家网络身份认证公共服务等方式，并禁止向未认证者提供信息发布服务。因此不能把“能用邮箱登录”推成“邮箱登录已满足服务实名义务”；条文也没有指定必须购买本机号一键登录产品。第十七条显著标识范围包括可能导致公众混淆或误认的智能对话、智能写作；第十九、二十条对具有舆论属性或社会动员能力的服务规定备案、安全评估。

来源：[中国政府网《互联网信息服务深度合成管理规定》](https://www.gov.cn/zhengce/zhengceku/2022-12/12/content_5731431.htm)，第九、十三、十六至二十、二十三条。2022-11-25 成文，2023-01-10 施行。置信度：官方明文；具体适用边界、单纯私密对话是否构成“信息发布”的个案认定未证实。

### 1.6 “大模型备案”、服务备案与应用登记不能混称

网信办已公布生成式 AI 服务备案信息，后续附件同时使用“已备案”和“已登记”两个名称。公告明文要求：已上线的生成式 AI 应用或功能，应在显著位置或产品详情页公示所使用的已备案服务情况，注明模型名称及备案号。不能把备案简称理解成对所有应用都只有一种“大模型许可证”，也不能将调用第三方模型推导为不需公示。

来源：[国家网信办《关于发布生成式人工智能服务已备案信息的公告》](https://www.cac.gov.cn/2024-04/02/c_1713729983803145.htm)。公告 2024-04-02；页面附有截至 2026 年 8 月的汇总附件。置信度：公示要求和两类名单的存在为官方明文；具体程序与第三方模型备案替代范围未证实。

## 2. 微信小程序

### 2.1 服务器域名

常规 `wx.request`、上传、下载只能使用预先配置的 HTTPS 服务器域名，WebSocket 使用 WSS；官方明确“域名必须经过 ICP 备案”，普通公网配置不得使用 IP/localhost，并须满足有效证书等条件。境外服务器不自动免除微信的平台域名要求。开发者工具/手机调试跳过校验不能证明正式发布可用。

来源：[微信《网络》服务器域名配置](https://developers.weixin.qq.com/miniprogram/dev/framework/ability/network.html)。页面最后编辑 2026-08-21；查阅 2026-11-07。置信度：官方明文。

### 2.2 小程序备案

微信有独立小程序备案流程，支持个人及非个人材料路径；信息填报、平台初审、工信部短信核验、通管局审核后取得小程序备案号，指引明确获号后才进入下一步版本发布等流程。网站备案不是小程序备案；工信部解释已有网站备案者只可复用主体信息，仍须补充 App 信息。2023—2024 年的过渡期不是 2026 年新应用可先运营的依据。

来源：[微信《小程序备案操作指引》](https://developers.weixin.qq.com/miniprogram/product/record/)、[工信部 App 备案通知官方解读](https://www.gov.cn/zhengce/202308/content_6897437.htm)。微信页面最后编辑 2026-08-18；工信部解读 2023-08-09。置信度：备案流程及两种备案区分为官方明文；未备案账号的 CI 开发接口封禁范围未证实。

### 2.3 个人主体类目

当前官方个人主体开放大类为物流服务、教育服务、生活服务、餐饮服务、旅游服务、工具、商业服务、体育，不是非个人表的全部类目。工具类包括办公、记账、日历、天气、图片处理、计算器、报价/比价、信息查询、预约/报名、健康管理、备忘录等；限制随子类目变化。个人表没有“深度合成—AI问答”，不能因为有办公类目便认定可绕过 AI 类目材料。

来源：[微信《小程序开放的服务类目》](https://developers.weixin.qq.com/miniprogram/product/material/)。最后编辑 2026-11-03。置信度：开放表及子类目范围为官方明文；具体产品只选办公类目即可通过 AI 审核未证实。

### 2.4 生成式 AI 对话的类目与资质

非个人表的准确类目名为**“深度合成—AI问答”**，适用文本深度合成技术。公开材料为两条路径二选一，不是全部叠加；生成内容须显著标注“AI生成”“人工智能生成”或同义提示。拟人情感陪伴另有“拟人化互动”类目及不同材料，不应直接套用普通问答规则。

| 技术路径 | 微信 AI 问答公开材料 |
| --- | --- |
| 自研 | 小程序主体的《互联网信息服务算法备案》，算法类型为生成合成类 |
| 第三方 | 技术主体的算法备案（生成合成类〔深度合成〕）+ 小程序主体与技术主体的合作协议；协议含算法名称、应用场景或备案编号相关内容 |

公开材料行未另列名为“大模型备案”的独立证书；不能据此说必须叠加“算法、深度合成、大模型三张证”，也不能反向说国家服务备案/登记无需办理。

来源：[微信服务类目表](https://developers.weixin.qq.com/miniprogram/product/material/)、[AI问答资质说明](https://developers.weixin.qq.com/miniprogram/product/material/shenduhecheng/Aiwenda)、[深度合成规定第十九条](https://www.gov.cn/zhengce/zhengceku/2022-12/12/content_5731431.htm)。类目表编辑 2026-11-03；资质说明未标日期，查阅 2026-11-07。置信度：微信公开材料为官方明文；全部监管手续不能仅凭类目表认定。

### 2.5 Linux 上的 miniprogram-ci

官方 `miniprogram-ci` 可不打开开发者工具，使用 Node 脚本/CLI 执行 `ci.preview`、`ci.upload`。官方发布包没有 `os` 限制，含 Linux 相关支持记录；本轮未用真实 AppID/密钥验证当前机器上传成功，不承诺所有发行版/CPU。前提是可用小程序 AppID、可编译项目、兼容 Node/依赖环境，以及后台生成的代码上传私钥；该私钥有预览/上传权限，不是 AppSecret。2.1.31 包的 Node engine 为 `>=16.1.0`，是该版本声明的下限。

IP 白名单：现行微信文档明确“可选择打开”，开启后只有白名单内 IP 能调用，官方建议默认开启；因此不是无条件必开的开关。业务 request 域名白名单与 CI 来源 IP 是两套东西。预览/上传不等于审核或公开发布。

来源：[微信 miniprogram-ci 文档](https://developers.weixin.qq.com/miniprogram/dev/devtools/ci.html)、[官方 npm 包版本元数据](https://registry.npmjs.org/miniprogram-ci/2.1.31)、[官方发布包](https://registry.npmjs.org/miniprogram-ci/-/miniprogram-ci-2.1.31.tgz)、[官方发布流程](https://developers.weixin.qq.com/miniprogram/dev/framework/quickstart/release.html)。CI 文档编辑 2026-08-21；2.1.31 发布 2026-03-12。置信度：CI 功能、密钥与白名单开关为官方明文；Linux 可用性为官方间接；当前环境实际预览/上传成功未证实。

## 3. ICP 备案与境外主机

### 3.1 境外主机能否申请网站 ICP 备案

阿里云明确：使用中国香港、海外节点无需网站 ICP 备案；在阿里云申请 ICP 备案必须关联或购买符合条件的中国内地节点资源，香港节点本身不能作为该接入商的备案资源。“域名注册在国内”也不等于具备备案接入条件。这是网站备案/接入规则，不是面向大陆用户的其他服务监管豁免，也不能据此免除 App 备案。

来源：[阿里云《备案服务器检查》](https://help.aliyun.com/zh/icp-filing/basic-icp-service/user-guide/icp-filing-server-access-information-check)、[《什么是 ICP 备案》](https://help.aliyun.com/zh/icp-filing/basic-icp-service/product-overview/what-is-an-icp-filing)。页面 last-modified 分别为 2026-11-04、2026-05-19；查阅 2026-11-07。置信度：官方明文（阿里云接入/申请条件）；“全国所有接入商在所有情形均不能办理”未作扩大断言。

### 3.2 大陆接入后反向代理境外源站

大陆服务器对外接入需完成相应网站备案；已有其他接入商备案时，在阿里云接入仍须办理接入备案；应保持真实接入信息，不能把“买一台大陆机器取得备案号后即撤掉接入”当作官方认可做法。阿里云明确取消接入且没有其他接入商时可能成为空壳网站。**未找到主管机关明确认定“大陆反向代理到境外业务源站”一律许可或一律禁止的官方条文**；不能将反代描述为保证合规的通用办法。实际对外域名、接入信息、服务内容与跨境数据处理条件须分别核实，备案号本身不是这些事项的许可。

来源：同上。置信度：大陆接入及信息维护要求为官方明文；反向代理组合的全国统一许可/禁止结论为未证实。

## 4. iOS App Store 与 TestFlight

### 4.1 中国大陆 App Store 的 App 备案号

Apple 的中国大陆供应说明明确“部分 App 必须具备有效的 ICP Filing Number”，备案号及 App 元数据须与工信部备案信息匹配，验证保存后显示在商店产品页。这是 App 备案信息，不应混称为必须取得经营性 ICP 许可证。Apple 页面使用“部分 App”，不能据此宣称所有离线 App 也无条件相同；最终适用分类需按审核个案确认。

来源：[Apple《App information》中国大陆供应章节](https://developer.apple.com/help/app-store-connect/reference/app-information/app-information/)、[中文页面](https://developer.apple.com/cn/help/app-store-connect/reference/app-information/app-information/)。Apple 页面未标修订日期；查阅 2026-11-07。工信部通知原文本轮返回 403，未假称逐字读到；[官方解读](https://www.gov.cn/zhengce/202308/content_6897437.htm)发布 2023-08-09。置信度：Apple 备案号要求为官方明文；具体应用审批结果未证实。

### 4.2 含生成式 AI 功能的额外要求

App Store 指南第 5 节要求符合分发地区全部法律；第 4 节所列中国 AI 法规义务不会因上架而豁免。深度合成规定第十三条要求应用分发平台核验深度合成 App 的安全评估、备案情况；2025 年标识办法第七条另要求核验标识材料。但 Apple 公开页面未给出“中国区所有生成式 AI App 一律须交哪套算法/大模型/应用登记材料”的统一清单；接入已备案模型是否免除本 App 其他手续也未证实。指南 5.1.2(i) 明确：向第三方（包括第三方 AI）分享个人数据前，须清楚披露并获得明确许可。

来源：[Apple 指南第 5 节](https://developer.apple.com/app-store/review/guidelines/#legal)、[5.1.2(i)](https://developer.apple.com/app-store/review/guidelines/#data-use-and-sharing)、[深度合成规定](https://www.gov.cn/zhengce/zhengceku/2022-12/12/content_5731431.htm)、[标识办法](https://www.cac.gov.cn/2025-03/14/c_1743654684782215.htm)。置信度：法律合规、分发平台核验及个人数据许可为官方明文；Apple 专项材料清单及模型备案替代关系未证实。

### 4.3 TestFlight 外部测试

指南 2.2 明确 TestFlight 分发应面向将来公开分发，且须遵守 App Review Guidelines；外部测试构建须经 TestFlight App Review，首个构建需要完整审核，同版本后续构建可能不需完整审核。本地法律责任仍适用；但“大陆外测必定核验与正式大陆上架完全相同的 ICP/AI 材料”以及“TestFlight 明确豁免这些材料”均未证实。

来源：[Apple 指南 2.2 Beta Testing](https://developer.apple.com/app-store/review/guidelines/#beta-testing)、[Invite external testers](https://developer.apple.com/help/app-store-connect/test-a-beta-version/invite-external-testers/)。未标修订日期；查阅 2026-11-07。置信度：指南适用与外测审核为官方明文；本地法律责任合读为官方间接；中国专项材料完全相同或豁免未证实。

### 4.4 第三方登录与 Sign in with Apple

当前指南 4.8 Login Services：以第三方/社交登录建立或认证 App 主账户时，还须提供另一种等效登录选项，满足三项条件：只收集姓名与邮箱；允许用户在开户时隐藏邮箱；未经同意不为广告收集 App 交互。现行条文没有直接点名必须使用 Sign in with Apple；普通邮箱或手机号登录也不能自动视为满足三项条件。例外包括完全自有账户系统、替代应用市场及其市场专用登录、必须使用已有教育/企业账户的教育/企业/商务 App、政府/行业支持的公民身份或电子身份、必须登录特定第三方服务账户以访问该服务内容的客户端。“商务 App”标签本身不充分证明企业账户例外。

来源：[Apple 指南 4.8 Login Services](https://developer.apple.com/app-store/review/guidelines/#login-services)。未标修订日期；查阅 2026-11-07。置信度：条款与例外为官方明文；具体 App 是否命中例外须按账户用途判断。

## 5. 登录渠道门槛

本节的账号实名、域名 DNS 验证、ICP 备案、运营商报备是不同要求；某产品允许个人注册，不等于已证明个人在所有 H5 场景均能通过运营商审核。

### 5.1 阿里云号码认证 H5 本机号登录

接入前提明确允许企业实名认证或个人实名认证；H5 须创建认证方案，登记页面地址、源地址及方案类型。中国移动 H5 能力须等待方案创建后的运营商审核生效。官方 H5 接入要求开启 SIM 数据、关闭 Wi-Fi，且需用户补齐手机号中间四位，不能理解成所有网络下完全免输入。已核对官方正文未明文写出“H5 必须 ICP 备案”“必须企业备案”“备案主体必须等于账号主体”三项规则，均为未证实；也不能据此保证境外未备案域名可获批准。

来源：[号码认证最佳实践](https://help.aliyun.com/zh/pnvs/use-cases/best-practices-for-user-authentication)、[认证方案管理](https://help.aliyun.com/zh/pnvs/user-guide/number-certification-program-management)、[H5 客户端接入](https://help.aliyun.com/zh/pnvs/developer-reference/h5-client-access)。页面 last-modified 依次 2026-09-21、2026-09-18、2026-08-19；查阅 2026-11-07。置信度：通用实名及 H5 登记、网络条件为官方明文；ICP/企业/主体一致的额外硬门槛未证实。

### 5.2 极光 H5 本机号登录

官方开通页允许个人实名认证或企业资质认证。Web 设置需登记上线/下线日期、集成页面地址、请求来源并提交审核；一键登录需设置 RSA 公钥并申请相应平台开通。当前 Web SDK v5.0.0+ 还要求添加白名单、报备版本和配置开发者域名；仅开启数据且关闭 Wi-Fi 时认证。未取得足以证明 H5 一律需要 ICP、企业备案或备案主体一致的官方条文；“运营商报备”不能直接当作“ICP备案”。

来源：[开通认证服务](https://docs.jiguang.cn/jverification/guideline/provisioning)、[认证设置](https://docs.jiguang.cn/jverification/console/jver_setting)、[Web SDK 集成指南](https://docs.jiguang.cn/jverification/client/web_guide)、[Web SDK 概述](https://docs.jiguang.cn/jverification/client/web_sdk)。前两页最近更新 2022-11-02；后两页 2026-09-02。置信度：所列公开条件为官方明文；ICP/企业备案/主体一致及当前个案通过结果未证实。

### 5.3 国内短信签名与个人验证码

阿里云国内短信自有签名需可报备的企业/组织资质，个人认证自用资质无法报备；个人账号可申请获授权的企业“他用资质”，须委托授权书。材料并非只限有限公司，官方包括事业单位等，也提到个体工商户无公章时可签名。国内短信授权申请限中国大陆公司；签名审核通过后仍须完成运营商实名报备，并有可用模板。

例外：阿里云“短信认证”明确个人实名认证用户可用系统预置签名和标准验证码模板，无需企业营业执照、自行申请资质/签名/模板；不支持自定义签名模板。这不能当作个人可注册自有品牌短信签名的证据，也不能混用两类产品 API。

来源：[签名实名制报备](https://help.aliyun.com/zh/sms/user-guide/real-name-reporting-of-sms-sign-name)、[资质材料说明](https://help.aliyun.com/zh/sms/user-guide/qualification-application-description)、[申请短信签名](https://help.aliyun.com/zh/sms/user-guide/create-signatures)、[个人开发者如何接入短信验证码服务](https://help.aliyun.com/zh/pnvs/use-cases/sms-verify-for-individual-developers)。页面元数据依次 2026-09-17、2026-10-15、2026-10-15、2026-08-10。置信度：官方明文（阿里云对应产品范围）；不是对全行业所有供应商材料的一致性保证。

### 5.4 微信内网页授权 OAuth

网页授权支持已认证服务号，另明文允许已认证的政府、事业单位、媒体类型公众号；普通个人订阅号不属于该范围。常规服务号面向企业/组织，不应收窄成只有有限公司。须配置“网页授权域名”，回调与配置匹配；域名配置不自动覆盖父域或其他子域。该能力用于微信客户端内访问第三方网页，不能等同外部浏览器扫码登录。

来源：[微信《网页授权》](https://developers.weixin.qq.com/doc/service/guide/h5/auth.html)、[服务号指南](https://developers.weixin.qq.com/doc/service/guide/)。授权页最后编辑 2026-07-04。置信度：账号范围与域名匹配为官方明文；ICP 及主体一致细则未证实。

### 5.5 微信开放平台网站应用扫码登录

须有审核通过的网站应用并取得 AppID/AppSecret，且微信登录能力申请通过；不能注册账号就直接接入。网站应用审核规范要求官网展示备案信息，网站登记表的备案与主办单位一致并规范填写 ICP 备案号；官网主体与认证主体不一致有授权书路径。回调域名/地址须按对应模式配置匹配。本轮没有核实到网站扫码登录完整、统一的主体资格清单，不能肯定个人可开，也不能把混合应用规范中的公司公章条文扩成所有非大陆公司一律禁止。

来源：[网站登录开发指南](https://developers.weixin.qq.com/doc/oplatform/Website_App/WeChat_Login/Wechat_Login.html)、[应用审核规范 2.1、4.1、4.5、8.2、8.5、8.6](https://developers.weixin.qq.com/doc/oplatform/Website_App/operation.html)、[网站应用管理 2.2/2.3](https://developers.weixin.qq.com/doc/oplatform/developers/product/webapp/)。依次最后编辑 2026-06-25、2026-03-19、2026-05-27。置信度：应用/能力审核、网站备案材料和匹配为官方明文；完整主体名单及纯扫码认证统一要求未证实。

### 5.6 邮件发信

- **Resend**：正式向产品用户发信需拥有并验证域名，设置 SPF、DKIM 等 DNS 记录；子域单独验证。`resend.dev` 只供向账号关联邮箱测试。官方明确所有账号（含免费）立即有生产访问权限，无 SES 式沙箱/生产审批，但仍受域名验证及额度限制。来源：[Add and verify a domain](https://resend.com/docs/add-a-domain)、[生产权限说明](https://resend.com/docs/knowledge-base/does-resend-require-production-approval)、[Terms of Service](https://resend.com/legal/terms-of-service)。未标可确认的发布日期；查阅 2026-11-07。置信度：域名验证、生产权限、测试限制及账号条款为官方明文；中国企业/ICP 普遍前提或永久免核验保证未证实。
- **Amazon SES（全球区域）**：发送前验证 identity，可选域名或邮箱地址，不是必须自有域名。新账户按区域处于沙箱，只能发给已验证收件人/模拟器，面向普通用户须申请 production access。AWS 开户还有邮箱、联系资料、有效支付方式及电话身份核验。来源：[Verified identities](https://docs.aws.amazon.com/ses/latest/dg/verify-addresses-and-domains.html)、[Request production access](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html)、[AWS 开户](https://docs.aws.amazon.com/accounts/latest/reference/getting-started.html)。未标可确认的修订日期；查阅 2026-11-07。置信度：身份验证、沙箱/生产准入、开户核验为官方明文；中国企业/ICP 普遍前提未证实。
- **阿里云邮件推送 DirectMail**：必须有发信域名并完成 DNS 验证；当前新域名需 SPF、DKIM、DMARC、MX 通过。域名可由其他注册商/DNS 服务商管理，不必在阿里云购买。阿里云通用账号政策要求购买产品/服务前实名认证；这是账号级政策，对 DirectMail 适用为跨文档推导。来源：[如何配置发信域名](https://help.aliyun.com/zh/direct-mail/user-guide/how-to-configure-sending-domain-names)、[实名认证概览](https://help.aliyun.com/zh/account/account-verification-overview)。依次更新 2026-04-15、2026-09-21。置信度：发信域名及账号通用规则为官方明文；账号规则套用于该产品为官方间接；仅企业、ICP 普遍门槛及个人产品准入保证未证实。

## 6. iOS PWA 能力边界

- **Web Push**：iOS/iPadOS 16.4 起支持添加到主屏幕的 Web App 接收 Web Push；不是普通 Safari 标签页直接等价可用。须是 Web App 形态（如 manifest 的 standalone/fullscreen），以用户直接交互触发许可请求并获准，配合 Push API、Notifications API、Service Worker 及服务端推送订阅；服务运行在安全上下文。无需 Apple Developer Program 会员。Apple 当前文档不支持 invisible push，接收后须展示通知。平台支持不等于已证明大陆网络送达率。来源：[WebKit 16.4 功能说明](https://webkit.org/blog/13966/webkit-features-in-safari-16-4/)、[Web Push for Web Apps on iOS and iPadOS](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/)、[Apple Web Push 文档](https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers)。2023-03-27 正式版说明；Apple 文档未标日期，查阅 2026-11-07。置信度：版本、主屏幕与授权前提为官方明文；中国大陆实际网络可达性与送达率未实测。
- **键盘上方表单辅助栏**：未找到 Apple 官方公开支持的网页 API 可隐藏 Safari/主屏幕 PWA 的整条上一项、下一项、完成等系统表单辅助栏；不能将“未找到”写成已严格证明永远不存在。`autocomplete`、`autocorrect`、输入类型的官方说明只涉及自动填充、纠错和键盘类型，不承诺隐藏整栏。UIKit 的 `inputAccessoryView` / `inputAssistantItem` 是原生接口，不能作为 iPhone PWA 网页接口。来源：[Safari Supported Attributes](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariHTMLRef/Articles/Attributes.html)、[Supported Input Types](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariHTMLRef/Articles/InputTypes.html)、[UITextInputAssistantItem](https://developer.apple.com/documentation/uikit/uitextinputassistantitem)。Safari 归档参考更新 2014-07-15；UIKit 文档未标日期。置信度：网页整栏隐藏 API 的存在为未证实；所列属性/原生 API 的用途为官方明文。
- **`apple-touch-startup-image`**：Apple 归档文档明确支持 iOS Web App 的启动图。因此“这只是社区技巧/Apple 从未支持”不对；但只凭该归档页，无法确认截至核查日所有当前 iOS/iPadOS 版本、尺寸、方向均继续可靠支持。不能把历史支持写成当前全量兼容保证，也不能把 manifest 图标等同于启动图。来源：[Apple Configuring Web Applications — Specifying a Launch Screen Image](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariWebContent/ConfiguringWebApplications/ConfiguringWebApplications.html)。归档文档更新 2016-12-12。置信度：历史支持为官方明文；“当前所有版本仍支持”未证实。

## 7. 常见说法与证据不一致处

1. “境外主机无 ICP，所以所有渠道/AI 法规都无门槛”不成立：备案接入、微信域名规则、App 备案和面向境内公众的 AI 监管是不同问题（1.1、2.1、3.1、4.1）。
2. “大陆反代境外就保证合规”未证实：取得备案不等于取得所有业务许可，也未找到一律允许/禁止这种代理组合的官方条文（3.2）。
3. “个人小程序只选办公就能上线 AI”未证实：个人开放表无 AI 问答，非个人 AI 问答有明确材料路径；这也不等于国家法规禁止个人提供任何 AI（2.3—2.4、1.1）。
4. “必须三张独立证”或“上游备案后应用全免”都不能据现有来源成立：算法、深度合成、服务备案/登记不能混称；微信第三方路径是技术方算法备案加合作协议（1.6、2.4）。
5. “Linux 没官方开发者工具就不能预览上传”与 CI 文档不符；但工具链支持不等于真实账号验证成功。“CI IP 白名单必须永远开启”也不符现行可选开关（2.5）。
6. “TestFlight 外测绕过审核和当地法律”不符指南 2.2；“外测必定逐项查同一套大陆材料”也未证实（4.3）。
7. “第三方登录无条件必须加 Apple 登录”不是当前 4.8 的准确表述：现行要求是满足三项条件的等效选项，并有例外（4.4）。
8. “邀请制、免费、人数少就自动豁免 AI 监管”无明文依据；非公众内部活动例外不能直接等同外部邀请码体验（1.4）。
9. “一键登录 H5 一律只准企业/域名一律须备案”证据不足：两家服务商均有允许个人实名的公开表述，具体 H5 运营商审批和 ICP 细则仍有缺口（5.1—5.2）。
10. “个人完全不能发国内验证码”不成立：自有签名组织资质，与阿里云支持个人的预置签名“短信认证”是不同产品（5.3）。
11. “微信网页授权=网站扫码登录、业务域名=OAuth 回调域名”不成立：账号权限、应用审核和域名配置分别核对（5.4—5.5）。
12. “所有邮件服务都必须自有域名/都无身份要求”不成立：Resend/DirectMail 要求域名，SES 允许验证邮箱；实名、开户核验、DNS 和 ICP 备案要区分。“能收邮箱验证码=已满足 AI 服务实名义务”也不能推出（1.5、5.6）。
13. “iPhone 普通网页在任何 iOS 都能 Web Push”不成立：官方最低 16.4、主屏幕 Web App 与用户手势授权有明确条件（6.1）。
14. “CSS/自动填充属性能隐藏整条键盘表单辅助栏”未证实；原生 UIKit API 不是网页 API（6.2）。
15. “Apple 从未支持启动图”不符归档文档；但归档文档也不能证明当前所有机型版本仍稳定兼容（6.3）。

## 8. 使用建议

- 先把发布渠道和登录方式定下来，再决定备案/资质投入；不要把“网站能打开”当作“可以公开运营”。
- 面向境内公众的 AI 功能，优先确认模型服务的备案/登记状态和公示要求；接入已备案模型不自动免除应用自身义务。
- 任何“邀请制/小范围/免费”的豁免说法，要求对方给出官方条文和适用范围；没有就按未证实处理。
- 这份材料是核查快照，不是法律意见。监管和平台规则会变，提交前以官方页面为准。
