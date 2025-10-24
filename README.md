# 使用示例

## 完整演示流程

### 步骤1: 打开4个终端窗口

#### 终端1 - 启动协调者
```bash
cd E:\5567-Lab-2
python coordinator.py
```

你会看到：
```
✓ 协调者启动在 localhost:5000
============================================================

可用命令:
        print("\nAvailable commands:")
        print("  list    - List all the participants")
        print("  tx      - Initiate new transactions")
        print("  crash   - Simulated crash")
        print("  recover - Recover from the crash")
        print("  status  - View the transaction status")
        print("  quit    - Exit")

coordinator>
```

#### 终端2 - 启动参与者P1
```bash
cd E:\5567-Lab-2
python participant.py P1 6001
```

你会看到：
```
✓ 参与者 'P1' 启动在 localhost:6001
✓ 已注册到协调者 localhost:5000
============================================================

可用命令:
        print("\nAvailable commands:")
        print("  status            - Check the status")
        print("  data              - View the submitted data")
        print("  cancommit vote yes/no     - Vote on the CanCommit voting transaction")
        print("  precommit vote yes/no     - Vote on the PreCommit voting transaction")
        print("  ack commit/abort  - Confirm COMMIT or ABORT")
        print("  crash             - Simulated crash")
        print("  recover           - Recover from the collapse")
        print("  fail              - Set the failure rate")
        print("  quit              - Exit")

P1>
```

#### 终端3 - 启动参与者P2
```bash
cd E:\5567-Lab-2
python participant.py P2 6002
```

#### 终端4 - 启动参与者P3
```bash
cd E:\5567-Lab-2
python participant.py P3 6003
```

### 步骤2: 查看已注册的参与者

在协调者终端输入：
```
coordinator> list
```

输出：
```
已注册参与者 (3):
  - P1 (localhost:6001)
  - P2 (localhost:6002)
  - P3 (localhost:6003)
```

### 步骤3: 发起一个成功的事务

在协调者终端：
```
coordinator> tx
请输入事务数据 (格式: key=value, 例: account=alice,amount=100):
data> account=alice,amount=100,operation=deposit
```

你会看到完整的3PC流程：
```
============================================================
开始新事务: a1b2c3d4
事务数据: {'account': 'alice', 'amount': '100', 'operation': 'deposit'}
参与者数量: 3
============================================================

[阶段 1/3] CanCommit阶段 (CanCommit)
------------------------------------------------------------
→ 发送CanCommit到 P1... ✓ VOTE_YES
→ 发送CanCommit到 P2... ✓ VOTE_YES
→ 发送CanCommit到 P3... ✓ VOTE_YES

投票结果: 3/3 同意

[阶段 2/3] PreCommit阶段 (PreCommit)
------------------------------------------------------------
→ 发送PreCommit到 P1... ✓ VOTE_YES
→ 发送PreCommit到 P2... ✓ VOTE_YES
→ 发送PreCommit到 P3... ✓ VOTE_YES

投票结果: 3/3 同意

[阶段 3/3] 提交阶段 (COMMIT)
------------------------------------------------------------
→ 发送COMMIT到 P1... ✓ ACK_COMMIT
→ 发送COMMIT到 P2... ✓ ACK_COMMIT
→ 发送COMMIT到 P3... ✓ ACK_COMMIT

============================================================
✓ 事务 a1b2c3d4 提交成功! (3/3 确认)
============================================================
```

同时，在各个参与者终端会看到：
```
← 收到: PREPARE (事务 a1b2c3d4)
  ✓ 准备成功，投票 YES

← 收到: COMMIT (事务 a1b2c3d4)
  ✓ 事务已提交
  数据: {'account': 'alice', 'amount': '100', 'operation': 'deposit'}
```

### 步骤4: 查看参与者数据

在任一参与者终端：
```
P1> data
```

输出：
```
已提交的事务数据 (1):
  a1b2c3d4: {'account': 'alice', 'amount': '100', 'operation': 'deposit'}
```

### 步骤5: 模拟失败场景

在P2 Vote no

再次在协调者发起事务：
```
coordinator> tx
data> account=bob,amount=50,operation=withdraw
```

这次你会看到事务被中止：
```
============================================================
开始新事务: e5f6g7h8
事务数据: {'account': 'bob', 'amount': '50', 'operation': 'withdraw'}
参与者数量: 3
============================================================

[阶段 1/3] CanCommit阶段 (CanCommit)
------------------------------------------------------------
→ 发送CanCommit到 P1... ✓ VOTE_NO
→ 发送CanCommit到 P2... ✓ VOTE_YES
→ 发送CanCommit到 P3... ✓ VOTE_YES

投票结果: 2/3 同意

[阶段 3/3] 中止阶段 (ABORT)
------------------------------------------------------------
→ 发送COMMIT到 P1... ✓ ACK_ABORT
→ 发送COMMIT到 P2... ✓ ACK_ABORT
→ 发送COMMIT到 P3... ✓ ACK_ABORT

============================================================
✗ 事务 e5f6g7h8 已中止
============================================================
```

在P2终端会看到：
```

← 收到: ABORT (事务 e5f6g7h8)
  ✓ 事务已中止
```

### 步骤6: 查看事务状态

在协调者终端：
```
coordinator> status
```

输出：
```
事务历史 (2):
  a1b2c3d4: COMMITTED - {'account': 'alice', 'amount': '100', 'operation': 'deposit'}
  e5f6g7h8: ABORTED - {'account': 'bob', 'amount': '50', 'operation': 'withdraw'}
```


## 关闭系统

在所有终端中输入 `quit` 命令，或按 Ctrl+C。

建议顺序：
1. 先关闭所有参与者
2. 最后关闭协调者

