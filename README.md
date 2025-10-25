# Usage Examples

## Complete Demonstration Process

### Step 1: Open 4 Terminal Windows

#### Terminal 1 - Start the Coordinator
```bash
cd E:\5567-Lab-2
python coordinator.py
```

You will see:
```
✓ The coordinator is started on localhost:5000
==============================================================

Available Commands:
print("\nAvailable commands:")
print(" list - List all the participants")
print(" tx - Initiate new transactions")
print(" crash - Simulated crash")
print(" recover - Recover from the crash")
print(" status - View the transaction status")
print(" quit - Exit")

coordinator>
```

#### Terminal 2 - Start participant P1
```bash
cd E:\5567-Lab-2
python participant.py P1 6001
```

You will see:
```
✓ Participant 'P1' started at localhost:6001
✓ Registered with coordinator localhost:5000
=============================================================

Available commands:
print("\nAvailable commands:")
print(" status - Check the status")
print(" data - View the submitted data")
print(" cancommit vote yes/no - Vote on the CanCommit voting transaction")
print(" precommit vote yes/no - Vote on the PreCommit voting transaction")
print(" ack commit/abort - Confirm COMMIT or ABORT")
print(" crash - Simulated crash")
print(" recover - Recover from the collapse")
print(" fail - Set the failure rate")
print(" quit - Exit")

P1>
```

#### Terminal 3 - Start participant P2
```bash
cd E:\5567-Lab-2
python participant.py P2 6002
```

#### Terminal 4 - Start participant P3
```bash
cd E:\5567-Lab-2
python participant.py P3 6003
```

### Step 2: View registered participants

In the coordinator terminal, enter:
```
coordinator> list
```

Output:
```
Registered participants (3):
- P1 (localhost:6001)
- P2 (localhost:6002)
- P3 (localhost:6003)
```

### Step 3: Initiate a successful transaction

On the coordinator terminal:
```
coordinator> tx
Please enter the transaction data (format: key=value, example: account=alice,amount=100):
data> account=alice,amount=100,operation=deposit
```

You will see the complete 3PC process:
```
= ... 3
============================================================

[Phase 1/3] CanCommit Phase (CanCommit)
------------------------------------------------------------
→ Send CanCommit to P1... ✓ VOTE_YES
→ Send CanCommit to P2... ✓ VOTE_YES
→ Send CanCommit to P3... ✓ VOTE_YES

Voting Result: 3/3 Agree

[Phase 2/3] PreCommit Phase (PreCommit)
------------------------------------------------------------
→ Send PreCommit to P1... ✓ VOTE_YES
→ Send PreCommit to P2... ✓ VOTE_YES
→ Send PreCommit to P3... ✓ VOTE_YES

Voting Result: 3/3 Agree

[Phase 3/3] Commit Phase (COMMIT)
------------------------------------------------------------
→ Send COMMIT to P1... ✓ ACK_COMMIT
→ Send COMMIT to P2... ✓ ACK_COMMIT
→ Send COMMIT to P3... ✓ ACK_COMMIT

===============================================================
✓ Transaction a1b2c3d4 Committed Successfully! (3/3 Confirmation)
===================================================================
```

At the same time, each participant will see the following on their terminal:
```
← Received: PREPARE (transaction a1b2c3d4)
✓ Prepared successfully, voted YES

← Received: COMMIT (transaction a1b2c3d4)
✓ Transaction committed
Data: {'account': 'alice', 'amount': '100', 'operation': 'deposit'}
```

### Step 4: View participant data

On any participant terminal:
```
P1> data
```

Output:
```
Committed transaction data (1):
a1b2c3d4: {'account': 'alice', 'amount': '100', 'operation': 'deposit'}
```

### Step 5: Simulate failure scenario

On P2 Vote no

Initiate transaction again on the coordinator:
```
coordinator> tx
data> account=bob,amount=50,operation=withdraw
```

This time you'll see the transaction aborted:
```
======================================================================
Start new transaction: e5f6g7h8
Transaction data: {'account': 'bob', 'amount': '50', 'operation': 'withdraw'}
Number of participants: 3
=================================================================

[Phase 1/3] CanCommit phase (CanCommit)
------------------------------------------------------------
→ Send CanCommit to P1... ✓ VOTE_NO
→ Send CanCommit to P2... ✓ VOTE_YES
→ Send CanCommit to P3... ✓ VOTE_YES

Voting result: 2/3 agree

[Phase 3/3] Abort phase (ABORT)
------------------------------------------------------------
→ Send COMMIT to P1... ✓ ACK_ABORT
→ Send COMMIT to P2... ✓ ACK_ABORT
→ Send COMMIT to P3... ✓ ACK_ABORT

================================================================
✗ Transaction e5f6g7h8 Aborted
==============================================================
```

You will see the following in the P2 terminal:
```

← Received: ABORT (transaction e5f6g7h8)
✓ Transaction aborted
```

### Step 6: View transaction status

In the coordinator terminal:
```
coordinator> status
```

Output:
```
Transaction history (2):
a1b2c3d4: COMMITTED - {'account': 'alice', 'amount': '100', 'operation': 'deposit'}
e5f6g7h8: ABORTED - {'account': 'bob', 'amount': '50', 'operation': 'withdraw'
```

## Shutdown the system

Enter the `quit` command in all terminals, or press Ctrl+C.

Recommended order:

1. Shut down all participants first

2. Shut down the coordinator last
