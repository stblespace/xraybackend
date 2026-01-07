import asyncio
from typing import Optional

import grpc
from google.protobuf import any_pb2, descriptor_pb2, descriptor_pool, symbol_database

from app.config import LOCALHOST_VALUES


HANDLER_SERVICE = "xray.app.proxyman.command.HandlerService"
ACCOUNT_TYPE_URL = "type.googleapis.com/xray.proxy.vless.Account"


class XrayClientError(Exception):
    """Raised when the Xray gRPC API returns an error we cannot safely ignore."""


def _ensure_descriptor(pool: descriptor_pool.DescriptorPool, file_proto: descriptor_pb2.FileDescriptorProto) -> None:
    """
    Idempotently register a file descriptor with the default pool.
    """

    try:
        pool.FindFileByName(file_proto.name)
    except KeyError:
        pool.Add(file_proto)


def _register_proto_definitions() -> None:
    """
    Define the minimal proto messages we need to talk to Xray's HandlerService.
    """

    pool = descriptor_pool.Default()

    # VLESS account message.
    try:
        pool.FindMessageTypeByName("xray.proxy.vless.Account")
    except KeyError:
        account_file = descriptor_pb2.FileDescriptorProto()
        account_file.name = "xray_proxy_vless.proto"
        account_file.package = "xray.proxy.vless"

        account_msg = account_file.message_type.add()
        account_msg.name = "Account"

        field = account_msg.field.add()
        field.name = "id"
        field.number = 1
        field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING

        field = account_msg.field.add()
        field.name = "flow"
        field.number = 2
        field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING

        field = account_msg.field.add()
        field.name = "encryption"
        field.number = 3
        field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING

        _ensure_descriptor(pool, account_file)

    # User message shared across inbound types.
    try:
        pool.FindMessageTypeByName("xray.common.protocol.User")
    except KeyError:
        user_file = descriptor_pb2.FileDescriptorProto()
        user_file.name = "xray_common_protocol.proto"
        user_file.package = "xray.common.protocol"
        user_file.dependency.append("google/protobuf/any.proto")

        user_msg = user_file.message_type.add()
        user_msg.name = "User"

        field = user_msg.field.add()
        field.name = "email"
        field.number = 1
        field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING

        field = user_msg.field.add()
        field.name = "level"
        field.number = 2
        field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        field.type = descriptor_pb2.FieldDescriptorProto.TYPE_UINT32

        field = user_msg.field.add()
        field.name = "alter_id"
        field.number = 3
        field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        field.type = descriptor_pb2.FieldDescriptorProto.TYPE_UINT32

        field = user_msg.field.add()
        field.name = "account"
        field.number = 4
        field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
        field.type_name = ".google.protobuf.Any"

        _ensure_descriptor(pool, user_file)

    # Handler service request/response messages.
    try:
        pool.FindMessageTypeByName("xray.app.proxyman.command.AddUserRequest")
    except KeyError:
        handler_file = descriptor_pb2.FileDescriptorProto()
        handler_file.name = "xray_proxyman_command.proto"
        handler_file.package = "xray.app.proxyman.command"
        handler_file.dependency.append("xray_common_protocol.proto")

        add_req = handler_file.message_type.add()
        add_req.name = "AddUserRequest"
        field = add_req.field.add()
        field.name = "tag"
        field.number = 1
        field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
        field = add_req.field.add()
        field.name = "user"
        field.number = 2
        field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
        field.type_name = ".xray.common.protocol.User"

        handler_file.message_type.add().name = "AddUserResponse"

        remove_req = handler_file.message_type.add()
        remove_req.name = "RemoveUserRequest"
        field = remove_req.field.add()
        field.name = "tag"
        field.number = 1
        field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
        field = remove_req.field.add()
        field.name = "email"
        field.number = 2
        field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING

        handler_file.message_type.add().name = "RemoveUserResponse"

        _ensure_descriptor(pool, handler_file)


_register_proto_definitions()
_SYMBOL_DB = symbol_database.Default()


class XrayClient:
    """
    Minimal async gRPC client for Xray's HandlerService.
    """

    def __init__(
        self,
        host: str,
        port: int,
        inbound_tag: str,
        account_type_url: str = ACCOUNT_TYPE_URL,
        handler_service: str = HANDLER_SERVICE,
        flow: str = "",
        encryption: str = "none",
    ) -> None:
        if host not in LOCALHOST_VALUES:
            raise XrayClientError("Xray gRPC must be accessed via localhost")

        self.target = f"{host}:{port}"
        self.inbound_tag = inbound_tag
        self.account_type_url = account_type_url
        self.handler_service = handler_service
        self.flow = flow or ""
        self.encryption = encryption or "none"

        self._channel: Optional[grpc.aio.Channel] = None
        self._add_user = None
        self._remove_user = None

        # Prototypes generated from the descriptors above.
        self.Account = _SYMBOL_DB.GetPrototype(
            descriptor_pool.Default().FindMessageTypeByName("xray.proxy.vless.Account")
        )
        self.User = _SYMBOL_DB.GetPrototype(
            descriptor_pool.Default().FindMessageTypeByName("xray.common.protocol.User")
        )
        self.AddUserRequest = _SYMBOL_DB.GetPrototype(
            descriptor_pool.Default().FindMessageTypeByName(
                "xray.app.proxyman.command.AddUserRequest"
            )
        )
        self.AddUserResponse = _SYMBOL_DB.GetPrototype(
            descriptor_pool.Default().FindMessageTypeByName(
                "xray.app.proxyman.command.AddUserResponse"
            )
        )
        self.RemoveUserRequest = _SYMBOL_DB.GetPrototype(
            descriptor_pool.Default().FindMessageTypeByName(
                "xray.app.proxyman.command.RemoveUserRequest"
            )
        )
        self.RemoveUserResponse = _SYMBOL_DB.GetPrototype(
            descriptor_pool.Default().FindMessageTypeByName(
                "xray.app.proxyman.command.RemoveUserResponse"
            )
        )

    async def start(self) -> None:
        if self._channel is not None:
            return

        self._channel = grpc.aio.insecure_channel(self.target)
        self._add_user = self._channel.unary_unary(
            f"/{self.handler_service}/AddUser",
            request_serializer=self.AddUserRequest.SerializeToString,
            response_deserializer=self.AddUserResponse.FromString,
        )
        self._remove_user = self._channel.unary_unary(
            f"/{self.handler_service}/RemoveUser",
            request_serializer=self.RemoveUserRequest.SerializeToString,
            response_deserializer=self.RemoveUserResponse.FromString,
        )

        await self._ensure_channel_ready()

    async def _ensure_channel_ready(self) -> None:
        if self._channel is None:
            raise XrayClientError("Xray gRPC channel not initialized")
        try:
            await asyncio.wait_for(self._channel.channel_ready(), timeout=2)
        except asyncio.TimeoutError as exc:
            raise XrayClientError("Timed out connecting to Xray gRPC") from exc
        except grpc.RpcError as exc:
            raise XrayClientError(exc.details() or str(exc)) from exc

    async def close(self) -> None:
        if self._channel:
            await self._channel.close()
            self._channel = None

    def _build_account_any(self, uuid: str) -> any_pb2.Any:
        """
        Create the Any-wrapped VLESS account payload for the given UUID.
        """

        account = self.Account()
        account.id = uuid
        if self.flow:
            account.flow = self.flow
        if self.encryption:
            account.encryption = self.encryption

        packed = any_pb2.Any()
        packed.Pack(account, type_url_prefix="type.googleapis.com")

        # Allow overriding the type URL to match deployments that use a different proto package.
        if self.account_type_url:
            packed.type_url = self.account_type_url

        return packed

    async def add_user(self, uuid: str) -> bool:
        """
        Add a VLESS user identified by the supplied UUID.
        Returns True if added, False if the user already existed.
        """

        if self._channel is None:
            await self.start()
        else:
            await self._ensure_channel_ready()

        user = self.User()
        user.email = uuid
        user.level = 0
        user.alter_id = 0
        user.account.CopyFrom(self._build_account_any(uuid))

        request = self.AddUserRequest()
        request.tag = self.inbound_tag
        request.user.CopyFrom(user)

        try:
            await self._add_user(request)
            return True
        except grpc.aio.AioRpcError as exc:
            details = (exc.details() or "").lower()
            if exc.code() == grpc.StatusCode.ALREADY_EXISTS or "exist" in details:
                return False

            raise XrayClientError(exc.details() or str(exc)) from exc

    async def remove_user(self, uuid: str) -> bool:
        """
        Remove a user; returns False when the user did not exist.
        """

        if self._channel is None:
            await self.start()
        else:
            await self._ensure_channel_ready()

        request = self.RemoveUserRequest()
        request.tag = self.inbound_tag
        request.email = uuid

        try:
            await self._remove_user(request)
            return True
        except grpc.aio.AioRpcError as exc:
            details = (exc.details() or "").lower()
            if exc.code() in (grpc.StatusCode.NOT_FOUND, grpc.StatusCode.FAILED_PRECONDITION) or "not found" in details:
                return False

            raise XrayClientError(exc.details() or str(exc)) from exc

    async def check_health(self) -> bool:
        try:
            if self._channel is None:
                await self.start()
            await self._ensure_channel_ready()
            return True
        except XrayClientError:
            return False
