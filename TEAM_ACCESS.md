# LC Audit Web — 团队使用说明

## 访问地址

| 场景 | 地址 |
|------|------|
| 本机访问 | http://localhost:5000 |
| 局域网访问（团队成员） | http://10.26.120.115:5000 |

> ⚠️ 团队成员访问需与服务器在**同一局域网**内。

---

## 服务状态

服务已配置为 **Windows 计划任务自动启动**，每次 Lucius 登录电脑时自动启动。

### 确认服务是否运行

在浏览器打开 http://10.26.120.115:5000，能看到页面即表示正常。

或在服务器上运行：
```powershell
netstat -ano | findstr ":5000"
```
看到 `LISTENING` 行表示服务运行中。

---

## 手动启停（仅服务器操作）

### 手动启动
```powershell
schtasks /Run /TN LCAuditWeb
```

### 停止服务
```powershell
# 查找进程 PID（LISTENING 行最后一列）
netstat -ano | findstr ":5000"
# 终止进程（替换 <PID> 为实际数字）
Stop-Process -Id <PID> -Force
```

### 开机自启说明

计划任务名称：`LCAuditWeb`  
触发时机：Lucius 账户登录时自动启动  
崩溃恢复：崩溃后 1 分钟自动重试，最多重试 99 次  

可在**任务计划程序**（`taskschd.msc`）中查看和管理。

---

## 查看日志

服务日志位于：
```
c:\Users\jason.lzx\WorkBuddy\20260422092630\lc-audit-web\server.log
```

日志自动轮转（最大 5MB × 3 份历史）。

---

## 常见问题

**Q: 团队成员打不开网页？**  
A: 确认 Lucius 的电脑已开机并已登录账户。服务随登录启动，不登录不运行。

**Q: 打开网页显示"拒绝连接"？**  
A: 服务器上执行 `schtasks /Run /TN LCAuditWeb` 手动启动。

**Q: 防火墙拦截了 5000 端口？**  
A: 通知 IT 在 Windows 防火墙开放入站规则 TCP 5000，或在 PowerShell（管理员）执行：
```powershell
New-NetFirewallRule -DisplayName "LC Audit Web" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow
```
