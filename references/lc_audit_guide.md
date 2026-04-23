# LC Audit Reference Guide (信用证审核参考指南)

## 1. SWIFT MT700 常用字段速查

| 字段 | 含义 | 审核要点 |
|------|------|---------|
| 27 | Sequence of Total | 确认是否为完整信用证（如 1/1） |
| 40A | Form of LC | IRREVOCABLE（不可撤销）/ IRREVOCABLE TRANSFERABLE（可转让） |
| 20 | LC Number | 所有单据上的L/C号必须与此一致 |
| 31C | Date of Issue | 开证日期 |
| 31D | Date and Place of Expiry | 到期日 + 到期地点（注意：交单须在到期地点完成） |
| 50 | Applicant | 申请人名称和地址，发票上的买方须与此一致 |
| 59 | Beneficiary | 受益人名称和地址，汇票/发票上的卖方须与此一致 |
| 32B | Currency Code, Amount | 信用证金额和币种，发票金额不得超出 |
| 39A | Percentage Credit Amount | 金额允许浮动的百分比（如 05/05 = ±5%） |
| 41A | Available With...By... | 议付行及方式（ANY BANK / Nominated Bank） |
| 42C | Drafts at... | 汇票期限（AT SIGHT即期 / XX DAYS AFTER B/L DATE延期） |
| 42A | Drawee | 汇票付款人 |
| 43P | Partial Shipments | ALLOWED / NOT ALLOWED |
| 43T | Transhipment | ALLOWED / NOT ALLOWED |
| 44A | Place of Taking in Charge / Dispatch | 起运地 |
| 44B | Place of Final Destination / For Transportation to | 目的地 |
| 44C | Latest Date of Shipment | 最迟装运日 |
| 44D | Shipment Period | 装运期（如与44C同时存在，以44C为准） |
| 45A | Description of Goods | 货物描述，发票须与此一致 |
| 46A | Documents Required | 所需单据清单，逐条审核 |
| 47A | Additional Conditions | 附加条件，常含银行费用、特殊要求等 |
| 71B | Charges | 费用承担条款 |
| 48 | Period for Presentation | 交单期（如 21 DAYS AFTER B/L DATE） |
| 49 | Confirmation Instructions | WITH / WITHOUT / MAY ADD |
| 78 | Instruction to Paying/Accepting/Negotiating Bank | 银行间指示（寄单、费用等） |
| 72 | Sender to Receiver Information | 银行间备注 |

## 2. 常见单据审核要点

### 2.1 汇票（Bill of Exchange / Draft）
- 金额须与发票一致（不得超出L/C金额）
- Drawee须与42A一致
- 付款期限须与42C一致
- 须注明L/C号码
- 须有受益人签署

### 2.2 商业发票（Commercial Invoice）
- 须由受益人签发（SIGNED）
- 金额不超过L/C金额
- 货物描述须与45A一致（UCP600允许比L/C描述简短，但不得矛盾）
- 须显示L/C号码
- 份数须符合46A要求

### 2.3 装箱单（Packing List）
- 件数/重量/体积须与提单一致
- 品名须与发票一致
- 份数须符合46A要求

### 2.4 海运提单（Bill of Lading）
- 须为 FULL SET（全套正本）
- 须注明 CLEAN ON BOARD（清洁已装船）
- 收货人（Consignee）须与46A完全一致
- 通知人（Notify Party）须与46A一致
- 运费条款（FREIGHT PREPAID / COLLECT）须与L/C一致
- 装运港/目的港须与44A/44B一致
- 签发日期不得超过最迟装运日（44C）
- 须由承运人或其代理签署

### 2.5 保险单（Insurance Document）
- 如L/C要求 CIF/CIP 条款下保险
- 保险金额通常为CIF价值的110%
- 须覆盖指定险种
- 须注明索赔地点

## 3. 关键时间节点计算

### 交单截止日
- 计算：提单签发日 + 交单期（通常21天，具体看48栏）
- 上限：不得超过L/C到期日（31D）
- **两者取较早者**

### 装运期
- 不得晚于最迟装运日（44C）
- 不得早于L/C开证日（通常无此限制，但需检查）

### 到期日
- 所有单据须在到期日前（或当日）在到期地点（31D）交单

## 4. 信用证原件处理

### Safe Custody（安全保管）
- 通知行通常将L/C原件存放在Safe Custody
- 受益人**无需**自行提交L/C原件
- 银行间交单时由通知行/议付行自行处理
- 如L/C条款中出现 "THE ORIGINAL OF THIS LETTER OF CREDIT MUST BE PRESENTED..."，
  这是对**议付行**的指示，不是对受益人的要求

## 5. 常见不符点清单

| 不符点类型 | 风险等级 | 常见原因 |
|-----------|---------|---------|
| 迟装运 | 🔴 极高 | B/L日期晚于最迟装运日 |
| 迟交单 | 🔴 高 | 交单日期超出提单日+交单期或L/C到期日 |
| 发票金额超支 | 🔴 高 | 发票总额超出L/C金额 |
| 货物描述不符 | 🟡 中 | 发票品名与L/C描述不一致 |
| 缺少签署 | 🟡 中 | 要求签署的单据未签署 |
| 单据份数不足 | 🟡 中 | 正本/副本数量不满足要求 |
| 运费条款错误 | 🟡 中 | B/L运费条款与L/C要求相反 |
| 收货人名称错误 | 🔴 高 | Consignee名称或NIT号码与L/C不一致 |
| 缺少信用证要求的信息 | 🟡 中 | 如缺少邮箱、电话等47A要求的信息 |
| 单据间数据不一致 | 🟡 中 | 发票件数与提单不一致等 |

## 6. UCP600 核心规则速查

- **第14条**：单据审核标准——单据须在表面上与L/C条款一致
- **第18条**：商业发票——必须由受益人出具，不需签署（除非L/C要求）
- **第20条**：提单——须表明承运人名称、签署、日期、on board notation
- **第14条b款**：交单期——不迟于装运日后21天，不迟于L/C到期日
- **第6条d款**：L/C须规定交单地点（到期地点）
- **第29条**：最迟装运日如为非银行工作日，可顺延至下一工作日
- **第16条**：不符单据处理——银行可拒付或在保留不符点下付款
