"""
3PC Protocol - Participant
"""
import socket
import threading
import time
import random
from protocol import Message, MessageType


class Participant:
    """Participant class"""
    
    def __init__(self, participant_id: str, host: str = 'localhost', port: int = 6000,
                 coordinator_host: str = 'localhost', coordinator_port: int = 5000,
                 failure_rate: float = 0.0):
        self.participant_id = participant_id
        self.host = host
        self.port = port
        self.coordinator_host = coordinator_host
        self.coordinator_port = coordinator_port
        self.failure_rate = failure_rate  # Simulation failure rate (0.0 - 1.0)

        self.waited_transactions = set()    # Transactions in Phase 1
        self.prepared_transactions = set()  # Transactions in Phase 2
        self.committed_transactions = {}    # Transactions in Phase 3
        self.aborted_transactions = set()   # Suspended transactions
        
        self.running = False
        self.crashed = False  # crash status flag
        self.server_socket = None
        self.lock = threading.Lock()
        self.pending_vote = None  # Store the transaction information to be voted on (transaction_id, data)
        self.pending_commit = None  # Store the COMMIT (transaction_id, data) to be confirmed
        self.pending_abort = None  # Store the ABORT (transaction_id, data) to be confirmed
        
    def start(self):
        """Start participants"""
        # Start the server
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        
        print(f"✓ Participant '{self.participant_id}' starts at {self.host}:{self.port}")
        
        # Register with the coordinator
        if self._register_to_coordinator():
            print(f"✓ Registered with the coordinator {self.coordinator_host}:{self.coordinator_port}")
        else:
            print(f"✗ Registration to the coordinator failed")
        
        print("=" * 60)
        
        # Start the listening thread
        listen_thread = threading.Thread(target=self._listen_for_requests)
        listen_thread.daemon = True # Set it as a daemon thread
        listen_thread.start()
        
        # Command-line interface
        self._command_interface()
    
    def _register_to_coordinator(self) -> bool:
        """Register with the coordinator"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self.coordinator_host, self.coordinator_port))
            
            # Send the registration information
            register_msg = f"REGISTER|{self.participant_id}|{self.host}|{self.port}"
            sock.sendall(register_msg.encode('utf-8'))
            
            response = sock.recv(1024).decode('utf-8')
            sock.close()
            
            return response == "OK"
        except Exception as e:
            print(f"Registration failed: {e}")
            return False
    
    def _listen_for_requests(self):
        """Listen for the coordinator's requests"""
        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                client_socket, addr = self.server_socket.accept()
                threading.Thread(
                    target=self._handle_request,
                    args=(client_socket,),
                    daemon=True # Set it as a daemon thread
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Monitoring error: {e}")
    
    def _handle_request(self, client_socket):
        """Handle the coordinator's request"""
        try:
            data = client_socket.recv(4096).decode('utf-8')
            if not data:
                return
            
            # If crashed, do not process any messages
            if self.crashed:
                print(f"  💥 Crashed. Ignore the message")
                return
            
            message = Message.from_json(data)
            response = self._process_message(message)
            
            if response:
                client_socket.sendall(response.to_json().encode('utf-8'))
        except Exception as e:
            print(f"Handle request error: {e}")
        finally:
            client_socket.close()
    
    def _process_message(self, message: Message) -> Message:
        """Process messages"""
        print(f"\n← Receive: {message.msg_type.value} (Transaction {message.transaction_id})")
        
        # Simulation failure
        if self.failure_rate > 0 and random.random() < self.failure_rate:
            print(f"  💥 Simulation failure (Fail rate: {self.failure_rate*100}%)")
            if message.msg_type == MessageType.CANCOMMIT:
                return Message(MessageType.CANCOMMIT_VOTE_NO, message.transaction_id)
            return None
        
        if message.msg_type == MessageType.CANCOMMIT: # can commit
            return self._handle_cancommit(message)
        elif message.msg_type == MessageType.PRECOMMIT: # pre commit
            return self._handle_precommit(message)
        elif message.msg_type == MessageType.COMMIT: # do commit
            return self._handle_commit(message)
        elif message.msg_type == MessageType.CANCOMMIT_ABORT: # abort
            return self._handle_cancommit_abort(message)
        elif message.msg_type == MessageType.PRECOMMIT_ABORT: # abort
            return self._handle_precommit_abort(message)
        elif message.msg_type == MessageType.ABORT: # abort
            return self._handle_abort(message)
        elif message.msg_type == MessageType.QUERY_STATE: # query state
            return self._handle_query_state(message)
        
        return None
    
    def _handle_cancommit(self, message: Message) -> Message:
        """Handle the preparation request cancommit- Wait for manual voting"""
        transaction_data = message.data
        
        # If there is a simulation failure rate, check whether it is automatically rejected
        if self.failure_rate > 0 and random.random() < self.failure_rate:
            print(f"  💥 Simulation failure (Fail rate: {self.failure_rate*100}%)")
            print(f"  Automatically voting cancommit vote no")
            return Message(MessageType.CANCOMMIT_VOTE_NO, message.transaction_id)
        
        # Save the transaction to be voted on and wait for the user to vote manually
        with self.lock:
            self.pending_vote = (message.transaction_id, transaction_data)
        
        print(f"  📋 Transaction data: {transaction_data}")
        print(f"  ⏳ Waiting for the voting decision...")
        print(f"  Please enter the command: cancommit vote yes 或 cancommit vote no")
        
        # Start a thread to wait for the vote. If it times out after 60 seconds, it will automatically vote for NO
        threading.Thread(
            target=self._wait_for_cancommit_vote,
            args=(message.transaction_id,),
            daemon=True
        ).start()
        
        # Returning None indicates that there is no response for the time being, waiting for the user to vote
        return None

    def _wait_for_cancommit_vote(self, transaction_id: str, timeout: int = 60):
        """Wait for the vote. If it exceeds the time limit, a NO will be automatically cast"""
        time.sleep(timeout)
        with self.lock:
            if self.pending_vote and self.pending_vote[0] == transaction_id:
                print(f"\n⏰ Voting timeout! Automatically voting cancommit vote no")
                self._send_cancommit_vote_to_coordinator(transaction_id, False)
                self.pending_vote = None

    def _handle_precommit(self, message: Message) -> Message:
        """Handle the preparation request precommit- wait for manual voting"""
        transaction_data = message.data

        # If there is a simulation failure rate, check whether it is automatically rejected
        if self.failure_rate > 0 and random.random() < self.failure_rate:
            print(f"  💥 Simulation failure (failure rate: {self.failure_rate * 100}%)")
            print(f"  Automatic voting: precommit vote no")
            return Message(MessageType.PRECOMMIT_VOTE_NO, message.transaction_id)

        # Save the transaction to be voted on and wait for the user to vote manually
        with self.lock:
            self.pending_vote = (message.transaction_id, transaction_data)

        print(f"  📋 Transaction data: {transaction_data}")
        print(f"  ⏳ Waiting for the voting decision...")
        print(f"  Please enter the command: precommit vote yes 或 precommit vote no")

        # Start a thread to wait for the vote. If it times out after 60 seconds, it will automatically vote for NO
        threading.Thread(
            target=self._wait_for_precommit_vote,
            args=(message.transaction_id,),
            daemon=True
        ).start()

        # Returning None indicates that there is no response for the time being, waiting for the user to vote
        return None
    
    def _wait_for_precommit_vote(self, transaction_id: str, timeout: int = 60):
        """Wait for the vote. If it exceeds the time limit, a NO will be automatically cast"""
        time.sleep(timeout)
        with self.lock:
            if self.pending_vote and self.pending_vote[0] == transaction_id:
                print(f"\n⏰ Voting timeout! Automatic voting: precommit vote no")
                self._send_precommit_vote_to_coordinator(transaction_id, False)
                self.pending_vote = None
    
    def _wait_for_ack_commit(self, transaction_id: str, timeout: int = 60):
        """Wait for COMMIT confirmation. An automatic ACK will be sent if the timeout occurs"""
        time.sleep(timeout)
        with self.lock:
            if self.pending_commit and self.pending_commit[0] == transaction_id:
                print(f"\n⏰ Confirm timeout! Automatic ACK COMMIT")
                self._send_ack_to_coordinator(transaction_id, MessageType.ACK_COMMIT)
                # Execution submission
                if transaction_id in self.prepared_transactions:
                    self.committed_transactions[transaction_id] = self.pending_commit[1]
                    self.prepared_transactions.remove(transaction_id)
                self.pending_commit = None
    
    def _wait_for_ack_abort(self, transaction_id: str, timeout: int = 30):
        """Wait for the ABORT confirmation. Automatically ACK if the timeout occurs"""
        time.sleep(timeout)
        with self.lock:
            if self.pending_abort and self.pending_abort[0] == transaction_id:
                print(f"\n⏰ Confirm timeout! Automatic ACK ABORT")
                self._send_ack_to_coordinator(transaction_id, MessageType.ACK_ABORT)
                # Execution suspension
                if transaction_id in self.prepared_transactions:
                    self.prepared_transactions.remove(transaction_id)
                self.aborted_transactions.add(transaction_id)
                self.pending_abort = None
    
    def _handle_commit(self, message: Message) -> Message:
        """Processing submission requests - Manual confirmation is required"""
        transaction_id = message.transaction_id
        transaction_data = message.data
        
        with self.lock:
            if transaction_id not in self.prepared_transactions:
                print(f"  ✗ The transaction is not prepared and the submission is refused")
                return Message(MessageType.ACK_ABORT, transaction_id)
            
            # Save the COMMIT to be confirmed
            self.pending_commit = (transaction_id, transaction_data)
        
        print(f"  📋 Received the COMMIT request")
        print(f"  Transaction data: {transaction_data}")
        print(f"  ⏳ Pending confirmation....")
        print(f"  Please enter the command: ack commit or ack abort")
        
        # Start the timeout thread (automatically ACK Commit after 60 seconds)
        threading.Thread(
            target=self._wait_for_ack_commit,
            args=(transaction_id,),
            daemon=True
        ).start()
        
        return None  # Do not respond immediately and wait for manual confirmation
    
    def _handle_cancommit_abort(self, message: Message) -> Message:
        """Handle cancommit abort requests - Manual confirmation is required"""
        transaction_id = message.transaction_id
        transaction_data = message.data
        
        with self.lock:
            # Save the cancommit ABORT to be confirmed
            self.pending_abort = (transaction_id, transaction_data)
        
        print(f"  📋 Received the CANCOMMIT_ABORT request")
        print(f"  Transaction data: {transaction_data}")
        print(f"  ⏳ Waiting for confirmation...")
        print(f"  Please enter the command: ack abort")
        
        # Start the timeout thread (automatically ACK after 30 seconds)
        threading.Thread(
            target=self._wait_for_ack_abort,
            args=(transaction_id,),
            daemon=True
        ).start()
        
        return None  # Do not respond immediately and wait for manual confirmation

    def _handle_precommit_abort(self, message: Message) -> Message:
        """Handle termination requests - Manual confirmation is required"""
        transaction_id = message.transaction_id
        transaction_data = message.data

        with self.lock:
            # Save the ABORT to be confirmed
            self.pending_abort = (transaction_id, transaction_data)

        print(f"  📋 Received the PRECOMMIT_ABORT request")
        print(f"  Transaction data: {transaction_data}")
        print(f"  ⏳ Waiting for confirmation...")
        print(f"  Please enter the command: ack abort")

        # Start the timeout thread (automatically ACK after 30 seconds)
        threading.Thread(
            target=self._wait_for_ack_abort,
            args=(transaction_id,),
            daemon=True
        ).start()

        return None  # Do not respond immediately and wait for manual confirmation

    def _handle_abort(self, message: Message) -> Message:
        """Handle cancommit abort requests - Manual confirmation is required"""
        transaction_id = message.transaction_id
        transaction_data = message.data

        with self.lock:
            # Save the docommit ABORT to be confirmed
            self.pending_abort = (transaction_id, transaction_data)

        print(f"  📋 Received an ABORT request")
        print(f"  Transaction data: {transaction_data}")
        print(f"  ⏳ Waiting for confirmation...")
        print(f"  Please enter the command: ack abort")

        # Start the timeout thread (automatically ACK after 30 seconds)
        threading.Thread(
            target=self._wait_for_ack_abort,
            args=(transaction_id,),
            daemon=True
        ).start()

        return None  # Do not respond immediately and wait for manual confirmation

    def _handle_query_state(self, message: Message) -> Message:
        """Handle status queries"""
        transaction_id = message.transaction_id
        
        with self.lock:
            # Check the transaction status
            if transaction_id in self.committed_transactions:
                status = 'COMMITTED'
                data = self.committed_transactions[transaction_id]
            elif transaction_id in self.prepared_transactions:
                status = 'PREPARED'
                data = {}
            elif transaction_id in self.waited_transactions:
                status = 'WAITED'
                data = {}
            elif transaction_id in self.aborted_transactions:
                status = 'ABORTED'
                data = {}
            else:
                status = 'UNKNOWN'
                data = {}
        
        print(f"  Status query: {status}")
        return Message(MessageType.STATE_RESPONSE, transaction_id, {'status': status, 'data': data})
    
    def _validate_transaction(self, data: dict) -> bool:
        """Verification transaction (customizable verification logic)"""
        # Example: Simply check if there is any data
        return len(data) > 0
    
    def _send_cancommit_vote_to_coordinator(self, transaction_id: str, vote_yes: bool):
        """Send the vote to the coordinator"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self.coordinator_host, self.coordinator_port))
            
            # Send the voting message "cancommit"
            if vote_yes:
                with self.lock:
                    self.waited_transactions.add(transaction_id)
                vote_msg = Message(MessageType.CANCOMMIT_VOTE_YES, transaction_id)
                print(f"  ✓ Voted CanCommit YES")
            else:
                vote_msg = Message(MessageType.CANCOMMIT_VOTE_NO, transaction_id)
                print(f"  ✗ Voted CanCommit NO")
            
            # Use a special mark to indicate that this is a delayed voting response
            vote_data = f"VOTE_RESPONSE|{self.participant_id}|{vote_msg.to_json()}"
            sock.sendall(vote_data.encode('utf-8'))
            sock.close()
        except Exception as e:
            print(f"Failed to send the vote: {e}")

    def _send_precommit_vote_to_coordinator(self, transaction_id: str, vote_yes: bool):
        """Send the vote to the coordinator"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self.coordinator_host, self.coordinator_port))

            # Send the voting message precommit
            if vote_yes:
                with self.lock:
                    if transaction_id in self.waited_transactions:
                        self.waited_transactions.remove(transaction_id)
                    self.prepared_transactions.add(transaction_id)
                vote_msg = Message(MessageType.PRECOMMIT_VOTE_YES, transaction_id)
                print(f"  ✓ Voted PreCommit YES")
            else:
                vote_msg = Message(MessageType.PRECOMMIT_VOTE_NO, transaction_id)
                print(f"  ✗ Voted PreCommit NO")

            # Use a special mark to indicate that this is a delayed voting response
            vote_data = f"VOTE_RESPONSE|{self.participant_id}|{vote_msg.to_json()}"
            sock.sendall(vote_data.encode('utf-8'))
            sock.close()
        except Exception as e:
            print(f"Failed to send the vote: {e}")
    
    def _send_ack_to_coordinator(self, transaction_id: str, ack_type: MessageType):
        """Send an ACK confirmation to the coordinator"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self.coordinator_host, self.coordinator_port))
            
            ack_msg = Message(ack_type, transaction_id)
            
            # Use a special tag to indicate that this is a delayed ACK response
            ack_data = f"ACK_RESPONSE|{self.participant_id}|{ack_msg.to_json()}"
            sock.sendall(ack_data.encode('utf-8'))
            sock.close()
            
            if ack_type == MessageType.ACK_COMMIT:
                print(f"  ✓ Confirmed COMMIT")
            else:
                print(f"  ✓ Confirmed ABORT")
        except Exception as e:
            print(f"Failed to send ACK: {e}")
    
    def _request_history_from_coordinator(self):
        """Request the historical log from the coordinator"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self.coordinator_host, self.coordinator_port))
            
            # Send historical requests
            history_msg = Message(MessageType.REQUEST_HISTORY, "HISTORY", {"participant_id": self.participant_id})
            request_data = f"HISTORY_REQUEST|{self.participant_id}|{history_msg.to_json()}"
            sock.sendall(request_data.encode('utf-8'))
            
            # Receive historical data
            response_data = sock.recv(65536).decode('utf-8')
            sock.close()
            
            if response_data:
                response = Message.from_json(response_data)
                if response.msg_type == MessageType.HISTORY_RESPONSE:
                    history = response.data.get('history', [])
                    print(f"\n📜 Obtained from the coordinator, {len(history)} historical records")
                    print(f"\n📜 The historical record is\n")
                    for record in history: # print the history
                        print(record)

                    # Synchronize historical data
                    with self.lock:
                        for record in history:
                            tx_id = record['transaction_id']
                            status = record['status']
                            data = record['data']
                            
                            if status == 'COMMITTED':
                                self.committed_transactions[tx_id] = data
                                if tx_id in self.prepared_transactions:
                                    self.prepared_transactions.remove(tx_id)
                            elif status == 'ABORTED':
                                self.aborted_transactions.add(tx_id)
                                if tx_id in self.prepared_transactions:
                                    self.prepared_transactions.remove(tx_id)
                    
                    print(f"  ✓ Historical data has been synchronized")
                    return True
        except Exception as e:
            print(f"Request history failed: {e}")
        return False
    
    def _command_interface(self):
        """Command-line interface"""
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
        print()
        
        while self.running:
            try:
                status_prefix = "💥CRASHED" if self.crashed else self.participant_id
                cmd = input(f"{status_prefix}> ").strip()
                
                if not cmd:
                    continue
                
                cmd_lower = cmd.lower()
                
                if cmd_lower == 'quit':
                    self.stop()
                    break
                elif cmd_lower == 'status':
                    self._show_status()
                elif cmd_lower == 'data':
                    self._show_data()
                elif cmd_lower.startswith('cancommit vote '):
                    self._handle_cancommit_vote_command(cmd)
                elif cmd_lower.startswith('precommit vote '):
                    self._handle_precommit_vote_command(cmd)
                elif cmd_lower.startswith('ack '):
                    self._handle_ack_command(cmd)
                elif cmd_lower == 'crash':
                    self._handle_crash()
                elif cmd_lower == 'recover':
                    self._handle_recover()
                elif cmd_lower == 'fail':
                    self._set_failure_rate()
                else:
                    print("Unknown command, please use: status, data, cancommit vote yes/no, precommit vote yes/no, ack commit/abort, crash, recover, fail, quit")
            except KeyboardInterrupt:
                print("\nUse the 'quit' command to exit")
            except Exception as e:
                print(f"Error: {e}")
    
    def _handle_cancommit_vote_command(self, cmd: str):
        """Handle the voting command Cancommit"""
        parts = cmd.strip().lower().split()
        if len(parts) != 3 or parts[2] not in ['yes', 'no']:
            print("Please input: cancommit vote yes or cancommit vote no")
            return
        
        with self.lock:
            if not self.pending_vote:
                print("There are no transactions to be voted on")
                return
            
            transaction_id, data = self.pending_vote
            cancommit_vote_yes = (parts[2] == 'yes')
            self.pending_vote = None
        
        print(f"\nVOted transaction {transaction_id}")
        print(f"  Data: {data}")
        self._send_cancommit_vote_to_coordinator(transaction_id, cancommit_vote_yes)

    def _handle_precommit_vote_command(self, cmd: str):
        """Handle the voting command Precommit"""
        parts = cmd.strip().lower().split()
        if len(parts) != 3 or parts[2] not in ['yes', 'no']:
            print("Please input: precommit vote yes or precommit vote no")
            return

        with self.lock:
            if not self.pending_vote:
                print("There are no transactions to be voted on")
                return

            transaction_id, data = self.pending_vote
            precommit_vote_yes = (parts[2] == 'yes')
            self.pending_vote = None

        print(f"\nVoted transaction {transaction_id}")
        print(f"  Data: {data}")
        self._send_precommit_vote_to_coordinator(transaction_id, precommit_vote_yes)

    def _handle_ack_command(self, cmd: str):
        """Handle the ACK confirmation command"""
        parts = cmd.strip().lower().split()
        if len(parts) != 2 or parts[1] not in ['commit', 'abort']:
            print("Please input: ack commit or ack abort")
            return
        
        ack_commit = (parts[1] == 'commit')
        
        with self.lock:
            # Check for any pending commits or ABORT
            if ack_commit:
                if not self.pending_commit:
                    print("There is no COMMIT to be confirmed")
                    return
                transaction_id, data = self.pending_commit
                self.pending_commit = None
                
                # Execution submission
                if transaction_id in self.prepared_transactions:
                    self.committed_transactions[transaction_id] = data
                    self.prepared_transactions.remove(transaction_id)
            else:
                # Users can reply "abort" to a COMMIT request or confirm an ABORT request
                if self.pending_commit:
                    transaction_id, data = self.pending_commit
                    self.pending_commit = None
                elif self.pending_abort:
                    transaction_id, data = self.pending_abort
                    self.pending_abort = None
                else:
                    print("There is no COMMIT or ABORT to be confirmed")
                    return
                
                # Execution suspension
                if transaction_id in self.prepared_transactions:
                    self.prepared_transactions.remove(transaction_id)
                self.aborted_transactions.add(transaction_id)
        
        print(f"\nConfirm the transaction {transaction_id}")
        print(f"  Data: {data}")
        
        # Send ACK
        if ack_commit:
            self._send_ack_to_coordinator(transaction_id, MessageType.ACK_COMMIT)
        else:
            self._send_ack_to_coordinator(transaction_id, MessageType.ACK_ABORT)
    
    def _handle_crash(self):
        """Handle crash commands"""
        if self.crashed:
            print("It is already in a state of crash")
            return
        
        self.crashed = True
        print(f"\n💥 {self.participant_id} Crashed！")
        print("  - No more messages will be received or processed")
        print("  - Use the 'recover' command to restore")
    
    def _handle_recover(self):
        """Handle the recovery command"""
        if not self.crashed:
            print("It is not currently in a state of crash")
            return
        
        print(f"\n🔄 Start to recover {self.participant_id}...")
        
        # Re-register with the coordinator
        if self._register_to_coordinator():
            print(f"  ✓ Re-registered with the coordinator")
        else:
            print(f"  ✗ Re-registration failed")
            return
        
        # Request historical log
        print("  📡 Requesting the history log...")
        if self._request_history_from_coordinator():
            self.crashed = False
            print(f"\n✓ {self.participant_id} It has been fully recovered!")
        else:
            print(f"  ✗ The historical synchronization failed, but it has been marked as a recovery status")
            self.crashed = False
    
    def _show_status(self):
        """Display status"""
        print(f"\nParticipant status:")
        print(f"  ID: {self.participant_id}")
        print(f"  Address: {self.host}:{self.port}")
        print(f"  Status: {'💥 Crashed' if self.crashed else '✓ Normal execution'}")
        print(f"  Fail rate: {self.failure_rate*100}%")
        
        with self.lock:
            has_pending = self.pending_vote is not None
            if has_pending:
                tx_id, data = self.pending_vote
                print(f"  Transactions  awaiting voting: {tx_id} - {data}")

        print(f"  Waited transactions: {len(self.waited_transactions)}")
        print(f"  Prepared transactions: {len(self.prepared_transactions)}")
        print(f"  committed transactions: {len(self.committed_transactions)}")
        print(f"  aborted transactions: {len(self.aborted_transactions)}")
    
    def _show_data(self):
        """Display the submitted data"""
        print(f"\nSubmitted transaction data ({len(self.committed_transactions)}):")
        if self.committed_transactions:
            for tx_id, data in self.committed_transactions.items():
                print(f"  {tx_id}: {data}")
        else:
            print("  (None)")
    
    def _set_failure_rate(self):
        """Set the fail rate"""
        try:
            rate = float(input("Input fail rate (0.0-1.0): "))
            if 0.0 <= rate <= 1.0:
                self.failure_rate = rate
                print(f"✓ The fail rate has been set to {rate*100}%")
            else:
                print("The fail rate must be between 0.0 and 1.0")
        except ValueError:
            print("Invalid value")
    
    def stop(self):
        """Stop participants"""
        print(f"\nParticipants {self.participant_id} are being closed...")
        self.running = False
        if self.server_socket:
            self.server_socket.close()


def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python participant.py <participant_id> [port] [coordinator_port]")
        print("Example: python participant.py P1 6001 5000")
        sys.exit(1)
    
    participant_id = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
    coordinator_port = int(sys.argv[3]) if len(sys.argv) > 3 else 5000
    
    participant = Participant(
        participant_id=participant_id,
        port=port,
        coordinator_port=coordinator_port
    )
    
    try:
        participant.start()
    except KeyboardInterrupt:
        participant.stop()


if __name__ == '__main__':
    main()

