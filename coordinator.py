"""
3PC协议 - Coordinator
"""
import socket
import threading
import time
import uuid
from typing import Dict, Set
from protocol import Message, MessageType


class Coordinator:
    """Coordinator class"""
    
    def __init__(self, host: str = 'localhost', port: int = 5000):
        self.host = host
        self.port = port
        self.participants: Dict[str, tuple] = {}  # {participant_id: (host, port)}
        self.transactions: Dict[str, dict] = {}  # trace the transaction status
        self.transaction_history = []  # historical logs (ordered by time)
        self.crashed = False  # crash flag
        self.lock = threading.Lock()
        self.running = False
        self.server_socket = None
        
    def start(self):
        """start the coordinator server"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        
        print(f"✓ The coordinator starts at {self.host}:{self.port}")
        print("=" * 60)
        
        # Start the listening thread
        listen_thread = threading.Thread(target=self._listen_for_participants)
        listen_thread.daemon = True
        listen_thread.start()
        
        # cmd terminal
        self._command_interface()
    
    def _listen_for_participants(self):
        """monitor the registration of the participants"""
        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                client_socket, addr = self.server_socket.accept()
                threading.Thread(
                    target=self._handle_participant_connection, # The function to be executed by the thread
                    args=(client_socket, addr), # The positional parameters (tuples) passed to the function can also be in the form of kwargs, that is, key-value.
                    daemon=True # The daemon thread ends immediately when the main thread ends, and the child thread ends immediately
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Monitor error: {e}")
    
    def _handle_participant_connection(self, client_socket, addr):
        """Handle participant connections"""
        try:
            data = client_socket.recv(65536).decode('utf-8')
            if not data:
                return
            
            parts = data.split('|')
            request_type = parts[0]

            # If the coordinator has crashed, most requests will not be processed (only registered and historical requests are allowed for recovery)
            if self.crashed and request_type not in ['REGISTER', 'HISTORY_REQUEST']:
                print(f"💥 The coordinator has collapsed and refused to handle it {request_type}")
                return
            
            if request_type == 'REGISTER' and len(parts) >= 4:
                # 注册请求格式: REGISTER|participant_id|host|port
                participant_id = parts[1]
                participant_host = parts[2]
                participant_port = int(parts[3])
                
                with self.lock:
                    self.participants[participant_id] = (participant_host, participant_port)
                
                print(f"✓ Participants have registered: {participant_id} ({participant_host}:{participant_port})")
                client_socket.sendall(b"OK")
                
            elif request_type == 'VOTE_RESPONSE' and len(parts) >= 3:
                # 延迟投票响应格式: VOTE_RESPONSE|participant_id|{message_json}
                participant_id = parts[1]
                message_json = '|'.join(parts[2:])  # 重新组合JSON部分（可能包含|字符）
                message = Message.from_json(message_json)
                
                print(f"← Received a delayed vote: {participant_id} - {message.msg_type.value} (transaction {message.transaction_id})")
                
                # 更新事务投票状态
                with self.lock:
                    if message.transaction_id in self.transactions:
                        tx = self.transactions[message.transaction_id]
                        if message.msg_type == MessageType.CANCOMMIT_VOTE_YES:
                            tx['votes'][participant_id] = True
                        elif message.msg_type == MessageType.CANCOMMIT_VOTE_NO:
                            tx['votes'][participant_id] = False
                        elif message.msg_type == MessageType.PRECOMMIT_VOTE_YES:
                            tx['votep'][participant_id] = True
                        else:
                            tx['votep'][participant_id] = False
            
            elif request_type == 'ACK_RESPONSE' and len(parts) >= 3:
                # 延迟ACK响应格式: ACK_RESPONSE|participant_id|{message_json}
                participant_id = parts[1]
                message_json = '|'.join(parts[2:])
                message = Message.from_json(message_json)
                
                print(f"← Receive a delayed ACK: {participant_id} - {message.msg_type.value} (transaction {message.transaction_id})")
                
                # 更新事务ACK状态
                with self.lock:
                    if message.transaction_id in self.transactions:
                        tx = self.transactions[message.transaction_id]
                        if 'acks' not in tx:
                            tx['acks'] = {}
                        tx['acks'][participant_id] = message.msg_type.value
                
            elif request_type == 'HISTORY_REQUEST' and len(parts) >= 2:
                # 历史请求格式: HISTORY_REQUEST|participant_id|{message_json}
                participant_id = parts[1]
                print(f"← Received historical requests: {participant_id}")
                
                # 发送历史日志
                with self.lock:
                    history_data = list(self.transaction_history)
                
                response = Message(
                    MessageType.HISTORY_RESPONSE,
                    "HISTORY",
                    {"history": history_data}
                )
                client_socket.sendall(response.to_json().encode('utf-8'))
                print(f"→ Send {len(history_data)} historical records to {participant_id}")
                
        except Exception as e:
            print(f"Handle participant connection errors: {e}")
        finally:
            client_socket.close()
    
    def _send_message(self, participant_id: str, message: Message, force: bool = False) -> Message:
        """Send a message to the participants and wait for a response
        
        Args:
            participant_id: participant ID
            message: The message to be sent
            force: Whether to force send (even crashed can be sent when used for recover)
        """
        if participant_id not in self.participants:
            raise Exception(f"Participant {participant_id} does not exist")
        
        # If crashed and it is not forced to send, refuse to send
        if self.crashed and not force:
            print(f"💥 The coordinator has crashed and is unable to send messages to {participant_id}")
            return None
        
        host, port = self.participants[participant_id]
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((host, port))
            sock.sendall(message.to_json().encode('utf-8'))
            
            response_data = sock.recv(4096).decode('utf-8')
            sock.close()
            
            if response_data:
                return Message.from_json(response_data)
            return None
        except Exception as e:
            print(f"Sending a message to {participant_id} fails: {e}")
            return None
    
    def execute_transaction(self, transaction_data: dict):
        """Execute 3PC transactions"""
        if self.crashed:
            print("❌ The coordinator has collapsed and is unable to initiate new transactions！")
            return False
            
        transaction_id = str(uuid.uuid4())[:8]
        
        print(f"\n{'='*60}")
        print(f"Start a new transaction: {transaction_id}")
        print(f"Transaction data: {transaction_data}")
        print(f"Number of participants: {len(self.participants)}")
        print(f"{'='*60}")
        
        if not self.participants:
            print("❌ There are no available participants!")
            return False
        
        # 初始化事务状态
        self.transactions[transaction_id] = {
            'data': transaction_data,
            'participants': list(self.participants.keys()),
            'votes': {},
            'votep': {},
            'votec': {},
            'acks': {},
            'status': 'WAITING'
        }
        
        # ============ Phase 1: Cancommit phase ============
        print(f"\n[Phase 1/3] Preparation Phase (CANCOMMIT)")
        print("-" * 60)
        
        cancommit_msg = Message(MessageType.CANCOMMIT, transaction_id, transaction_data)
        precommit_msg = Message(MessageType.PRECOMMIT, transaction_id, transaction_data)
        votes = {}
        votep = {}
        votec = {}
        participant_list = list(self.participants.keys())
        
        # Send a CANCOMMIT request (participants will vote manually and will not respond immediately)
        self.transactions[transaction_id]['status'] = 'WAITING'
        for participant_id in participant_list:
            print(f"→ Send CANCOMMIT to {participant_id}...", end=" ")
            response = self._send_message(participant_id, cancommit_msg)
            
            # Some participants may respond immediately (if a failure rate is set)
            if response:
                if response.msg_type == MessageType.CANCOMMIT_VOTE_YES:
                    votes[participant_id] = True
                    print("✓ CanCommit VOTE_YES (Immediately)")
                elif response.msg_type == MessageType.CANCOMMIT_VOTE_NO:
                    votes[participant_id] = False
                    print("✗ CanCommit VOTE_NO (Immediately)")
                elif response.msg_type == MessageType.PRECOMMIT_VOTE_YES:
                    votep[participant_id] = True
                    print("✓ PreCommit VOTE_NO (Immediately)")
                else:
                    votep[participant_id] = False
                    print(f"✗ {response.msg_type.value} (Immediately)")
            else:
                # There was no immediate response. Wait for manual voting
                print("⏳ Wait for manual voting...")
        
        self.transactions[transaction_id]['votes'] = votes


        # Wait for all participants to vote CanCommit (up to 60 seconds)
        print(f"\n⏳ Wait for all participants to vote...")
        wait_time = 0
        max_wait = 60
        while wait_time < max_wait:
            # Check if it has crashed
            if self.crashed:
                print(f"\n💥 The coordinator has crashed! Transaction {transaction_id} crashes in stage 1")
                print(f"  Participants are in a waiting state...")
                return False
            
            with self.lock:
                current_votes = self.transactions[transaction_id]['votes']
                if len(current_votes) == len(participant_list):
                    break
            
            time.sleep(1)
            wait_time += 1
            
            # The progress is displayed every five seconds
            if wait_time % 5 == 0:
                with self.lock:
                    current_votes = self.transactions[transaction_id]['votes']
                print(f"  Receive {len(current_votes)}/{len(participant_list)} votes ({wait_time}s)")
        
        # Get the final voting result
        with self.lock:
            votes = self.transactions[transaction_id]['votes']
        
        # Participants who fail to vote within the time limit will be regarded as having voted NO
        for participant_id in participant_list:
            if participant_id not in votes:
                votes[participant_id] = False
                print(f"✗ {participant_id} voting time exceeds the limit, it will be regarded as NO")

        
        # 决定是否precommit
        all_yes = all(votes.values())
        self.transactions[transaction_id]['status'] = 'WAITED'
        print(f"\nVoting result for CanCommit: {sum(votes.values())}/{len(votes)} Agree")

        if (all_yes):
            # ============ Phase 2: PreCommit phase ============
            self.transactions[transaction_id]['status'] = 'PREPARING'
            for participant_id in participant_list:
                print(f"→ Send PRECOMMIT to {participant_id}...", end=" ")
                response = self._send_message(participant_id, precommit_msg)  # send precommit message

                # Some participants may respond immediately (if a failure rate is set)
                if response:
                    if response.msg_type == MessageType.CANCOMMIT_VOTE_YES:
                        votes[participant_id] = True
                        print("✓ CanCommit VOTE_YES (Immediately)")
                    elif response.msg_type == MessageType.CANCOMMIT_VOTE_NO:
                        votes[participant_id] = False
                        print("✗ CanCommit VOTE_NO (Immediately)")
                    elif response.msg_type == MessageType.PRECOMMIT_VOTE_YES:
                        votep[participant_id] = True
                        print("✓ PreCommit VOTE_NO (Immediately)")
                    else:
                        votep[participant_id] = False
                        print(f"✗ {response.msg_type.value} (Immediately)")
                else:
                    # There was no immediate response. Wait for manual voting
                    print("⏳ Waiting for manual voting...")

            self.transactions[transaction_id]['votep'] = votep

            # Wait for all participants to vote PreCommit (up to 60 seconds)
            print(f"\n⏳ Waiting for all participants to vote for PreCommit...")
            wait_time = 0
            max_wait = 60
            while wait_time < max_wait:
                # 检查是否crash
                if self.crashed:
                    print(f"\n💥 The coordinator has crashed! Transaction {transaction_id} crashes in phase 2")
                    print(f"  Participants are in a waiting state...")
                    return False

                with self.lock:
                    current_votep = self.transactions[transaction_id]['votep']
                    if len(current_votep) == len(participant_list):
                        break

                time.sleep(1)
                wait_time += 1

                # The progress is displayed every five seconds
                if wait_time % 5 == 0:
                    with self.lock:
                        current_votep = self.transactions[transaction_id]['votep']
                    print(f"  Receive {len(current_votep)}/{len(participant_list)} votes ({wait_time}s)")

            # Get the final voting result
            with self.lock:
                votep = self.transactions[transaction_id]['votep']

            # Participants who fail to vote within the time limit will be regarded as having voted NO
            for participant_id in participant_list:
                if participant_id not in votep:
                    votep[participant_id] = False
                    print(f"✗ {participant_id} voting time exceeds the time limit，Regard as NO")

            self.transactions[transaction_id]['votep'] = votep

            # Decide whether to submit
            all_yes = all(votep.values())
            self.transactions[transaction_id]['status'] = 'PREPARED'
            print(f"\n Voting result for Precommit: {sum(votep.values())}/{len(votep)} agree")

            # ============ Phase 3: Submit/Abort Phase ============
            # Check if it crashes between stage 1 and stage 3
            if self.crashed:
                print(f"\n💥 The coordinator crashes after making a decision! Transaction {transaction_id} status is not determined")
                print(f"  Participants may be in a prepared state...")
                return False

            if all_yes:
                print(f"\n[Phase 3/3] COMMIT Phase")
                print("-" * 60)
                self.transactions[transaction_id]['status'] = 'COMMITTING'

                commit_msg = Message(MessageType.COMMIT, transaction_id, transaction_data)
                acks = {}

                # Send a COMMIT message (participants will manually ACK and will not respond immediately)
                for participant_id in self.participants.keys():
                    # Check for a crash before sending
                    if self.crashed:
                        print(f"\n💥 The coordinator has collapsed! Some participants did not receive the COMMIT")
                        return False

                    print(f"→ Send COMMIT to {participant_id}...", end=" ")
                    response = self._send_message(participant_id, commit_msg)

                    # Some participants might respond immediately
                    if response and response.msg_type == MessageType.ACK_COMMIT:
                        acks[participant_id] = 'ACK_COMMIT'
                        print("✓ ACK_COMMIT (Immediately)")
                    else:
                        print("⏳ Wait for manual ACK...")

                self.transactions[transaction_id]['acks'] = acks

                # Wait for all participants to ACK (up to 60 seconds)
                print(f"\n⏳ Waiting for all participants to ACK...")
                wait_time = 0
                max_wait = 60
                while wait_time < max_wait:
                    # Check if it has crashed
                    if self.crashed:
                        print(f"\n💥 The coordinator crashed while waiting for ACK!")
                        return False

                    with self.lock:
                        current_acks = self.transactions[transaction_id]['acks']
                        if len(current_acks) == len(participant_list):
                            print(f"  Receive {len(current_acks)}/{len(participant_list)} ACK responses ({wait_time}s)")
                            break

                    time.sleep(1)
                    wait_time += 1

                    # The progress is displayed every five seconds
                    if wait_time % 5 == 0:
                        with self.lock:
                            current_acks = self.transactions[transaction_id]['acks']
                        print(f"  Receive {len(current_acks)}/{len(participant_list)} ACK responses ({wait_time}s)")

                # Obtain the final ACK result
                with self.lock:
                    acks = self.transactions[transaction_id]['acks']

                # For participants who timeout but do not ACK, it is marked as timeout
                for participant_id in participant_list:
                    if participant_id not in acks:
                        acks[participant_id] = 'TIMEOUT'
                        print(f"✗ {participant_id} ACK timeout")

                self.transactions[transaction_id]['acks'] = acks
                success_count = sum(1 for ack in acks.values() if ack == 'ACK_COMMIT')

                # do commit no
                if success_count < len(participant_list):

                    self.transactions[transaction_id]['status'] = 'ABORTED'

                    # Record in the historical log
                    with self.lock:
                        self.transaction_history.append({
                            'transaction_id': transaction_id,
                            'status': 'ABORTED',
                            'data': transaction_data,
                            'timestamp': time.time()
                        })

                    print(f"\n{'=' * 60}")
                    print(f"✗ Transaction {transaction_id} is aborted，Because {(len(participant_list) - success_count)} participants' votes are Abort")
                    print(f"{'=' * 60}")
                    return False
                else:
                    self.transactions[transaction_id]['status'] = 'COMMITTED'

                    # 记录到历史日志
                    with self.lock:
                        self.transaction_history.append({
                            'transaction_id': transaction_id,
                            'status': 'COMMITTED',
                            'data': transaction_data,
                            'timestamp': time.time()
                        })

                    print(f"\n{'=' * 60}")
                    print(f"✓ Transaction {transaction_id} are committed successfully! ({success_count}/{len(self.participants)} confirm)")
                    print(f"{'=' * 60}")
                    return True
            else:
                print(f"\n[Phase 3/3] PRECOMMIT ABORT")
                print("-" * 60)
                self.transactions[transaction_id]['status'] = 'ABORTING'

                abort_msg = Message(MessageType.PRECOMMIT_ABORT, transaction_id, transaction_data)
                acks = {}

                # Send the PRECOMMIT ABORT message (participants will manually ACK and will not respond immediately)
                for participant_id in self.participants.keys():
                    # Check for a crash before sending
                    if self.crashed:
                        print(f"\n💥 The coordinator has collapsed! Some participants did not receive the PRECOMMIT ABORT")
                        return False

                    print(f"→ Send PRECOMMIT ABORT to {participant_id}...", end=" ")
                    response = self._send_message(participant_id, abort_msg)

                    # Some participants might respond immediately
                    if response and response.msg_type == MessageType.ACK_ABORT:
                        acks[participant_id] = 'ACK_ABORT'
                        print("✓ ACK_ABORT (Immediately)")
                    else:
                        print("⏳ Wait for manual ACK...")

                self.transactions[transaction_id]['acks'] = acks

                # Wait for all participants to ACK (up to 60 seconds)
                print(f"\n⏳ Waiting for all participants to ACK...")
                wait_time = 0
                max_wait = 60
                while wait_time < max_wait:
                    # Check if it has crashed
                    if self.crashed:
                        print(f"\n💥 The coordinator crashed while waiting for ACK!")
                        return False

                    with self.lock:
                        current_acks = self.transactions[transaction_id]['acks']
                        if len(current_acks) == len(participant_list):
                            print(f"  Receive {len(current_acks)}/{len(participant_list)} ACK responses ({wait_time}s)")
                            break

                    time.sleep(1)
                    wait_time += 1

                    # The progress is displayed every five seconds
                    if wait_time % 5 == 0:
                        with self.lock:
                            current_acks = self.transactions[transaction_id]['acks']
                        print(f"  Receive {len(current_acks)}/{len(participant_list)} ACK responses ({wait_time}s)")

                # Obtain the final ACK result
                with self.lock:
                    acks = self.transactions[transaction_id]['acks']

                # For participants who timeout but do not ACK, it is marked as timeout
                for participant_id in participant_list:
                    if participant_id not in acks:
                        acks[participant_id] = 'TIMEOUT'
                        print(f"✗ {participant_id} ACK Timeout")

                self.transactions[transaction_id]['acks'] = acks
                success_count = sum(1 for ack in acks.values() if ack == 'ACK_ABORT')

                self.transactions[transaction_id]['status'] = 'ABORTED'

                # Record in the historical log
                with self.lock:
                    self.transaction_history.append({
                        'transaction_id': transaction_id,
                        'status': 'ABORTED',
                        'data': transaction_data,
                        'timestamp': time.time()
                    })

                print(f"\n{'=' * 60}")
                print(f"✗ Transaction {transaction_id} is aborted")
                print(f"{'=' * 60}")
                return False
        else:
            print(f"\n[Phase 3/3] Abort Phase (CANCOMMIT_ABORT)")
            print("-" * 60)
            self.transactions[transaction_id]['status'] = 'ABORTING'

            abort_msg = Message(MessageType.CANCOMMIT_ABORT, transaction_id, transaction_data)
            acks = {}

            # Send the CANCOMMIT ABORT message (participants will manually ACK and will not respond immediately)
            for participant_id in self.participants.keys():
                # Check for a crash before sending
                if self.crashed:
                    print(f"\n💥 The coordinator has crashed! Some participants did not receive CANCOMMIT ABORT")
                    return False

                print(f"→ Send CANCOMMIT ABORT to {participant_id}...", end=" ")
                response = self._send_message(participant_id, abort_msg)

                # Some participants might respond immediately
                if response and response.msg_type == MessageType.ACK_ABORT:
                    acks[participant_id] = 'ACK_ABORT'
                    print("✓ ACK_ABORT (Immediately)")
                else:
                    print("⏳ Wait for manual ACK...")

            self.transactions[transaction_id]['acks'] = acks

            # Wait for all participants to ACK (up to 60 seconds)
            print(f"\n⏳ Waiting for all participants to ACK...")
            wait_time = 0
            max_wait = 60
            while wait_time < max_wait:
                # Check if it has crashed
                if self.crashed:
                    print(f"\n💥 The coordinator crashed while waiting for ACK!")
                    return False

                with self.lock:
                    current_acks = self.transactions[transaction_id]['acks']
                    if len(current_acks) == len(participant_list):
                        print(f"  Receive {len(current_acks)}/{len(participant_list)} ACK responses ({wait_time}s)")
                        break

                time.sleep(1)
                wait_time += 1

                # The progress is displayed every five seconds
                if wait_time % 5 == 0:
                    with self.lock:
                        current_acks = self.transactions[transaction_id]['acks']
                    print(f"  Receive {len(current_acks)}/{len(participant_list)} ACK responses ({wait_time}s)")

            # Obtain the final ACK result
            with self.lock:
                acks = self.transactions[transaction_id]['acks']

            # For participants who timeout but do not ACK, it is marked as timeout
            for participant_id in participant_list:
                if participant_id not in acks:
                    acks[participant_id] = 'TIMEOUT'
                    print(f"✗ {participant_id} ACK Timeout")

            self.transactions[transaction_id]['acks'] = acks
            success_count = sum(1 for ack in acks.values() if ack == 'ACK_ABORT')

            self.transactions[transaction_id]['status'] = 'ABORTED'

            # Record in the historical log
            with self.lock:
                self.transaction_history.append({
                    'transaction_id': transaction_id,
                    'status': 'ABORTED',
                    'data': transaction_data,
                    'timestamp': time.time()
                })

            print(f"\n{'=' * 60}")
            print(f"✗ Transaction {transaction_id} is aborted")
            print(f"{'=' * 60}")
            return False
    
    def _query_participant_state(self, participant_id: str, transaction_id: str) -> dict:
        """Query the status of participants regarding specific transactions"""
        try:
            query_msg = Message(MessageType.QUERY_STATE, transaction_id, {})
            # When using recover, it is necessary to force the sending of messages
            response = self._send_message(participant_id, query_msg, force=True)
            
            if response and response.msg_type == MessageType.STATE_RESPONSE:
                return response.data
            return {'status': 'UNKNOWN'}
        except Exception as e:
            print(f"  Query {participant_id} status is failed: {e}")
            return {'status': 'UNKNOWN'}
    
    def _recover_coordinator(self):
        """The coordinator recovered from the crashed status"""
        print(f"\n🔄 Start Coordinator recovery...")
        print("=" * 60)

        # Search for unfinished transactions
        with self.lock:
            unfinished_txs = {
                tx_id: tx_info 
                for tx_id, tx_info in self.transactions.items()
                if tx_info['status'] in ['WAITING', 'WAITED', 'PREPARING', 'PREPARED'] # , 'COMMITTING', 'ABORTING', 'COMMITTED', 'ABORTED'
            }
        
        if not unfinished_txs:
            print("✓ There are no unfinished tasks")
            self.crashed = False
            return

        self.crashed = False
        print(f"Find {len(unfinished_txs)} unfinished transactions")
        print()
        
        for tx_id, tx_info in unfinished_txs.items():
            print(f"\nHandle transactions {tx_id}:")
            print(f"  Status: {tx_info['status']}")
            print(f"  Data: {tx_info['data']}")
            
            # 查询所有参与者的状态
            print(f"  Query the status of participants...")
            participant_states = {}
            for participant_id in tx_info['participants']:
                if participant_id not in self.participants:
                    print(f"    {participant_id}: unregistered participant")
                    continue
                
                state = self._query_participant_state(participant_id, tx_id)
                participant_states[participant_id] = state
                print(f"    {participant_id}: {state.get('status', 'UNKNOWN')}")
            
            # How to handle it depends on the status
            waiting_count = sum(1 for s in participant_states.values()
                               if s.get('status') == 'WAITING' or s.get('status') == 'WAITED')
            prepared_count = sum(1 for s in participant_states.values()
                                 if s.get('status') == 'PREPARING' or s.get('status') == 'PREPARED')
            committed_count = sum(1 for s in participant_states.values() if s.get('status') == 'COMMITTING'
                                  or s.get('status') == 'COMMITTED')
            aborted_count = sum(1 for s in participant_states.values() 
                              if s.get('status') == 'ABORTING' or s.get('status') == 'ABORTED')
            
            print(f"\n  Status summary:")
            print(f"    WAITING: {waiting_count}")
            print(f"    PREPARED: {prepared_count}")
            print(f"    COMMITTED: {committed_count}")
            print(f"    ABORTED: {aborted_count}")
            
            # 决策逻辑
            if tx_info['status'] == 'WAITING' or tx_info['status'] == 'WAITED':
                # crash in cancommit
                print(f"  💡 Decision: Cancommit If the vote is not completed or is rejected, send an ABORT")
                self._complete_abort(tx_id, tx_info)
            elif tx_info['status'] == 'PREPARING' or tx_info['status'] == 'PREPARED':
                # crash during the Precommit stage to check the voting situation
                votes = tx_info.get('votes', {})
                if len(votes) == len(tx_info['participants']) and all(votes.values()):
                    # Everyone has voted YES, but no COMMIT has been sent yet. Send the COMMIT now
                    print(f"  💡 Decision: All participants are ready to send the COMMIT")
                    self._complete_commit(tx_id, tx_info)
                else:
                    # If the voting is not completed or there is a "NO", send "ABORT"
                    print(f"  💡 Decision: If the voting is not completed or there is a rejection, send ABORT")
                    self._complete_abort(tx_id, tx_info)
                    
            elif tx_info['status'] == 'COMMITTING' or tx_info['status'] == 'COMMITTED':
                # It crashed during the submission phase
                if committed_count > 0:
                    # Some participants have already submitted. Continue committing
                    print(f"  💡 Decision: Some participants have already submitted. Continue to send commits")
                    self._complete_commit(tx_id, tx_info)
                elif prepared_count == len(tx_info['participants']):
                    # All participants are in a prepared state and continue committing
                    print(f"  💡 Decision: All participants are ready to continue sending commits")
                    self._complete_commit(tx_id, tx_info)
                else:
                    # The status is inconsistent. Try committing
                    print(f"  💡 Decision: Attempt to complete the COMMIT")
                    self._complete_commit(tx_id, tx_info)
                    
            elif tx_info['status'] == 'ABORTING' or tx_info['status'] == 'ABORTED':
                # If it crashes during the ABORT phase, continue to abort
                print(f"  💡 Decision: Continue sending ABORT")
                self._complete_abort(tx_id, tx_info)
        
        self.crashed = False
        print(f"\n{'='*60}")
        print("✓ The coordinator's recovery is complete!")
        print(f"{'='*60}")
    
    def _complete_commit(self, transaction_id: str, tx_info: dict):
        """Complete the submission operation"""
        commit_msg = Message(MessageType.COMMIT, transaction_id, tx_info['data'])
        success_count = 0
        acks ={}

        # Send a COMMIT message (participants will manually ACK and will not respond immediately)
        for participant_id in self.participants.keys():
            # Check for a crash before sending
            if self.crashed:
                print(f"\n💥 The coordinator has collapsed! Some participants did not receive the COMMIT")
                return False

            print(f"→ Send COMMIT to {participant_id}...", end=" ")
            response = self._send_message(participant_id, commit_msg)

            # Some participants might respond immediately
            if response and response.msg_type == MessageType.ACK_COMMIT:
                acks[participant_id] = 'ACK_COMMIT'
                print("✓ ACK_COMMIT (Immedaitely)")
            else:
                print("⏳ Wait for manual ACK...")

        self.transactions[transaction_id]['acks'] = acks

        # Wait for all participants to ACK (up to 60 seconds)
        print(f"\n⏳ Waiting for all participants to ACK...")
        wait_time = 0
        max_wait = 60
        while wait_time < max_wait:
            # Check if it has crashed
            if self.crashed:
                print(f"\n💥 The coordinator crashed while waiting for ACK!")
                return False

            with self.lock:
                current_acks = self.transactions[transaction_id]['acks']
                if len(current_acks) == len(self.participants):
                    print(f"  Receive {len(current_acks)}/{len(self.participants)} ACK responses ({wait_time}s)")
                    break

            time.sleep(1)
            wait_time += 1

            # The progress is displayed every five seconds
            if wait_time % 5 == 0:
                with self.lock:
                    current_acks = self.transactions[transaction_id]['acks']
                print(f"  Receive {len(current_acks)}/{len(self.participants)} ACK responses ({wait_time}s)")

        # Obtain the final ACK result
        with self.lock:
            acks = self.transactions[transaction_id]['acks']

        # For participants who timeout but do not ACK, it is marked as timeout
        for participant_id in self.participants:
            if participant_id not in acks:
                acks[participant_id] = 'TIMEOUT'
                print(f"✗ {participant_id} ACK A Timeout")

        self.transactions[transaction_id]['acks'] = acks
        success_count = sum(1 for ack in acks.values() if ack == 'ACK_COMMIT')

        # do commit no
        if success_count < len(self.participants):

            self.transactions[transaction_id]['status'] = 'ABORTED'

            # Record in the historical log
            with self.lock:
                self.transaction_history.append({
                    'transaction_id': transaction_id,
                    'status': 'ABORTED',
                    'data': tx_info['data'],
                    'timestamp': time.time()
                })

            print(f"\n{'=' * 60}")
            print(f"✗ Transaction {transaction_id} is aborted，Because {(len(self.participants) - success_count)} participants vote the Abort")
            print(f"{'=' * 60}")
            return False
        else:
            self.transactions[transaction_id]['status'] = 'COMMITTED'

            # Record in the historical log
            with self.lock:
                self.transaction_history.append({
                    'transaction_id': transaction_id,
                    'status': 'COMMITTED',
                    'data': tx_info['data'],
                    'timestamp': time.time()
                })

            print(f"\n{'=' * 60}")
            print(f"✓ Transaction {transaction_id} is committed successfully! ({success_count}/{len(self.participants)} confirm)")
            print(f"{'=' * 60}")
    
    def _complete_abort(self, transaction_id: str, tx_info: dict):
        """Complete the termination operation"""
        abort_msg = Message(MessageType.ABORT, transaction_id, tx_info['data'])
        success_count = 0

        print("-" * 60)
        self.transactions[transaction_id]['status'] = 'ABORTING'

        acks = {}

        # Send the PRECOMMIT ABORT message (participants will manually ACK and will not respond immediately)
        for participant_id in self.participants.keys():

            print(f"→ 发送ABORT到 {participant_id}...", end=" ")
            response = self._send_message(participant_id, abort_msg)

            # Some participants might respond immediately
            if response and response.msg_type == MessageType.ACK_ABORT:
                acks[participant_id] = 'ACK_ABORT'
                print("✓ ACK_ABORT (Immediately)")
            else:
                print("⏳ Wait for manual ACK...")

        self.transactions[transaction_id]['acks'] = acks

        # Wait for all participants to ACK (up to 60 seconds)
        print(f"\n⏳ Waiting for all participants to ACK...")
        wait_time = 0
        max_wait = 60
        while wait_time < max_wait:
            # Check if it has crashed
            if self.crashed:
                print(f"\n💥 The coordinator crashed while waiting for ACK!")
                return False

            with self.lock:
                current_acks = self.transactions[transaction_id]['acks']
                if len(current_acks) == len(self.participants):
                    print(f"  Receive {len(current_acks)}/{len(self.participants)} ACK responses ({wait_time}s)")
                    break

            time.sleep(1)
            wait_time += 1

            # The progress is displayed every five seconds
            if wait_time % 5 == 0:
                with self.lock:
                    current_acks = self.transactions[transaction_id]['acks']
                print(f"  Receive {len(current_acks)}/{len(self.participants)} ACK respsponses ({wait_time}s)")

        # Obtain the final ACK result
        with self.lock:
            acks = self.transactions[transaction_id]['acks']

        # For participants who timeout but do not ACK, it is marked as timeout
        for participant_id in self.participants:
            if participant_id not in acks:
                acks[participant_id] = 'TIMEOUT'
                print(f"✗ {participant_id} ACK Timeout")

        self.transactions[transaction_id]['acks'] = acks
        success_count = sum(1 for ack in acks.values() if ack == 'ACK_ABORT')

        self.transactions[transaction_id]['status'] = 'ABORTED'

        # Record in the historical log
        with self.lock:
            self.transaction_history.append({
                'transaction_id': transaction_id,
                'status': 'ABORTED',
                'data': tx_info['data'],
                'timestamp': time.time()
            })

        print(f"\n{'=' * 60}")
        print(f"✗ Transaction {transaction_id} is aborted")
        print(f"{'=' * 60}")
        return False

    
    def _command_interface(self):
        """Command-line interface"""
        print("\nAvailable commands:")
        print("  list    - List all the participants")
        print("  tx      - Initiate new transactions")
        print("  crash   - Simulated crash")
        print("  recover - Recover from the crash")
        print("  status  - View the transaction status")
        print("  quit    - Exit")
        print()
        
        while self.running:
            try:
                status_prefix = "💥CRASHED" if self.crashed else "coordinator"
                cmd = input(f"{status_prefix}> ").strip().lower()
                
                if cmd == 'quit':
                    self.stop()
                    break
                elif cmd == 'list':
                    self._list_participants()
                elif cmd == 'tx':
                    self._start_transaction()
                elif cmd == 'crash':
                    self._handle_crash()
                elif cmd == 'recover':
                    self._handle_recover()
                elif cmd == 'status':
                    self._show_status()
                else:
                    print("For unknown commands, please use: list, tx, crash, recover, status, quit")
            except KeyboardInterrupt:
                print("\nUse the 'quit' command to exit")
            except Exception as e:
                print(f"Error: {e}")
    
    def _handle_crash(self):
        """Handle crash commands"""
        if self.crashed:
            print("It is already in a state of crash")
            return
        
        self.crashed = True
        print(f"\n💥 The coordinator has crashed!")
        print("  - New transactions cannot be initiated")
        print("  - Unfinished transactions will be suspended")
        print("  - Participants may be in a waiting state")
        print("  - Use the 'recover' command to restore")
    
    def _handle_recover(self):
        """Handle the recovery command"""
        if not self.crashed:
            print("It is not currently in a state of crash")
            return
        
        self._recover_coordinator()
    
    def _list_participants(self):
        """List all the participants"""
        print(f"\nRegistered participants ({len(self.participants)}):")
        if self.participants:
            for pid, (host, port) in self.participants.items():
                print(f"  - {pid} ({host}:{port})")
        else:
            print("  (None)")
    
    def _start_transaction(self):
        """Initiate new transactions"""
        print("\nPlease enter the transaction data (Format: key=value, e.g., account=alice, amount=100):")
        data_str = input("data> ").strip()
        
        if not data_str:
            print("Transaction data cannot be empty")
            return
        
        # Parse data
        transaction_data = {}
        for pair in data_str.split(','):
            if '=' in pair:
                key, value = pair.split('=', 1)
                transaction_data[key.strip()] = value.strip()
        
        if transaction_data:
            # Execute transactions in the background thread so that the command-line interface can continue to receive commands (such as crash).
            tx_thread = threading.Thread(
                target=self.execute_transaction,
                args=(transaction_data,),
                daemon=True
            )
            tx_thread.start()
            print("✓ The transaction has been started in the background. You can enter the 'crash' command at any time to simulate a crash")
        else:
            print("Invalid data format")
    
    def _show_status(self):
        """Display transaction status"""
        print(f"\nTransaction history ({len(self.transactions)}):")
        if self.transactions:
            for tx_id, tx_info in self.transactions.items():
                print(f"  {tx_id}: {tx_info['status']} - {tx_info['data']}")
        else:
            print("  (None)")
    
    def stop(self):
        """Stop coordinator"""
        print("\nThe coordinator is being shut down...")
        self.running = False
        if self.server_socket:
            self.server_socket.close()


def main():
    import sys
    
    port = 5000
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    
    coordinator = Coordinator(port=port)
    try:
        coordinator.start()
    except KeyboardInterrupt:
        coordinator.stop()


if __name__ == '__main__':
    main()

