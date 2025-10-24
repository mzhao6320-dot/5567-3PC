"""
2PC协议消息定义和常量
"""
import json
from enum import Enum


class MessageType(Enum):
    """消息类型"""
    # 协调者 -> 参与者
    PREPARE = "PREPARE"           # 准备阶段请求
    COMMIT = "COMMIT"             # 提交请求
    CANCOMMIT = "CanCommit"       # can commit, phase 1
    PRECOMMIT = "PreCommit"       # pre commit, phase 2
    DOCOMMIT = "DoCommit"         # do commit, phase 3
    ABORT = "ABORT"               # 中止请求
    CANCOMMIT_ABORT = "CANCOMMIT_ABORT"  # 中止请求
    PRECOMMIT_ABORT = "PRECOMMITABORT"  # 中止请求
    HISTORY_RESPONSE = "HISTORY_RESPONSE"  # 历史日志响应
    QUERY_STATE = "QUERY_STATE"   # 查询参与者状态
    
    # 参与者 -> 协调者
    CANCOMMIT_VOTE_YES = "CANCOMMIT_VOTE_YES"         # Cancommit 投票YES
    CANCOMMIT_VOTE_NO = "CANCOMMIT_VOTE_NO"           # Cancommit 投票NO
    PRECOMMIT_VOTE_YES = "PRECOMMIT_VOTE_YES"  # Cancommit 投票YES
    PRECOMMIT_VOTE_NO = "PRECOMMIT_VOTE_NO"  # Cancommit 投票NO
    ACK_COMMIT = "ACK_COMMIT"     # 确认提交
    ACK_ABORT = "ACK_ABORT"       # 确认中止
    REQUEST_HISTORY = "REQUEST_HISTORY"    # 请求历史日志
    STATE_RESPONSE = "STATE_RESPONSE"      # 状态响应


class Message:
    """消息类"""
    def __init__(self, msg_type: MessageType, transaction_id: str, data: dict = None):
        self.msg_type = msg_type
        self.transaction_id = transaction_id
        self.data = data or {}
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps({
            'msg_type': self.msg_type.value,
            'transaction_id': self.transaction_id,
            'data': self.data
        })
    
    @staticmethod
    def from_json(json_str: str):
        """从JSON字符串解析"""
        data = json.loads(json_str)
        return Message(
            MessageType(data['msg_type']),
            data['transaction_id'],
            data.get('data', {})
        )
    
    def __repr__(self):
        return f"Message({self.msg_type.value}, {self.transaction_id})"

