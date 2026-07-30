import struct
import time


FRAME_HEADER = b"\xFF\xFF"
SYSTEM_ID = 0xFF


class NexArmCommand:
    CMD_FIRMWARE_VERSION_CHECK = 0x01
    CMD_CHECK_BAT_LEVEL_CHECK = 0x02
    CMD_ACTION_GROUP_RUN = 0x03
    CMD_ACTION_GROUP_STOP = 0x04
    CMD_COORDINATE_SET = 0x08
    CMD_BUZZER_SET = 0x09
    CMD_GET_CUR_COORDS = 0x0B
    CMD_STEPPER_RUN = 0x13
    CMD_ACTION_GROUP_ERASE = 0x17
    CMD_SET_ESPNOW_CHANNEL = 0x1E
    CMD_SET_GLOBAL_ACC = 0x1F
    CMD_ESPNOW_SYNC_CTRL = 0x21
    CMD_MECANUM_CONTROL = 0x22
    CMD_ARM_MOVE_INC = 0x32


class ServoRegister:
    WRITE = 0x03
    TORQUE = 0x28
    ACC = 0x29
    POS = 0x2A
    SPEED = 0x2E


class NexArmPacket:
    def __init__(self, packet_id, length, cmd, payload, checksum):
        self.packet_id = packet_id
        self.length = length
        self.cmd = cmd
        self.payload = payload
        self.checksum = checksum


class NexArmCurrentCoords:
    def __init__(
        self,
        x,
        y,
        z,
        pitch=None,
        roll=None,
        claw=None,
        servo_positions=(),
    ):
        self.x = x
        self.y = y
        self.z = z
        self.pitch = pitch
        self.roll = roll
        self.claw = claw
        self.servo_positions = servo_positions

    def __repr__(self):
        return (
            "NexArmCurrentCoords("
            "x={0}, y={1}, z={2}, pitch={3}, roll={4}, claw={5}, servo_positions={6})"
        ).format(
            self.x,
            self.y,
            self.z,
            self.pitch,
            self.roll,
            self.claw,
            self.servo_positions,
        )


class NexArmClient:
    def __init__(self, port, baudrate=1000000, timeout=0.1, write_timeout=0.1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.serial = None

    def open(self):
        if self.serial and self.serial.is_open:
            return
        import serial  # Jetson: pip install pyserial

        self.serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
            write_timeout=self.write_timeout,
        )

    def close(self):
        if self.serial and self.serial.is_open:
            self.serial.close()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _ensure_open(self):
        if not self.serial or not self.serial.is_open:
            self.open()
        return self.serial

    @staticmethod
    def _checksum(packet_id, length, cmd, payload):
        total = packet_id + length + cmd + sum(payload)
        return (~total) & 0xFF

    @classmethod
    def build_frame(cls, packet_id, cmd, payload=b""):
        length = len(payload) + 2
        checksum = cls._checksum(packet_id, length, cmd, payload)
        return FRAME_HEADER + bytes([packet_id, length, cmd]) + payload + bytes([checksum])

    def send_frame(self, packet_id, cmd, payload=b""):
        ser = self._ensure_open()
        frame = self.build_frame(packet_id, cmd, payload)
        ser.write(frame)
        ser.flush()
        return frame

    def read_packet(self, timeout=None):
        ser = self._ensure_open()
        if timeout is None:
            timeout = self.timeout
        deadline = time.monotonic() + timeout

        state = 0
        packet_id = 0
        length = 0
        cmd = 0
        payload = bytearray()

        while time.monotonic() < deadline:
            chunk = ser.read(1)
            if not chunk:
                continue
            byte = chunk[0]

            if state == 0:
                if byte == 0xFF:
                    state = 1
                continue
            if state == 1:
                if byte == 0xFF:
                    state = 2
                else:
                    state = 0
                continue
            if state == 2:
                packet_id = byte
                state = 3
                continue
            if state == 3:
                length = byte
                if length < 2:
                    state = 0
                else:
                    state = 4
                continue
            if state == 4:
                cmd = byte
                payload = bytearray()
                if length > 2:
                    state = 5
                else:
                    state = 6
                continue
            if state == 5:
                payload.append(byte)
                if len(payload) == length - 2:
                    state = 6
                continue
            if state == 6:
                checksum = byte
                expected = self._checksum(packet_id, length, cmd, bytes(payload))
                if checksum != expected:
                    raise ValueError(
                        "Checksum mismatch: got 0x{0:02X}, expected 0x{1:02X}".format(
                            checksum, expected
                        )
                    )
                return NexArmPacket(packet_id, length, cmd, bytes(payload), checksum)

        raise TimeoutError("Timed out waiting for NexArm packet")

    def request(
        self,
        packet_id,
        cmd,
        payload=b"",
        expect_reply=False,
        expected_cmd=None,
        expected_ids=(),
        timeout=None,
    ):
        self.send_frame(packet_id, cmd, payload)
        if not expect_reply:
            return None

        if expected_cmd is None:
            expected_cmd = cmd
        if timeout is None:
            timeout = self.timeout

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            packet = self.read_packet(timeout=max(0.01, deadline - time.monotonic()))
            if packet.cmd != expected_cmd:
                continue
            if expected_ids and packet.packet_id not in expected_ids:
                continue
            return packet
        raise TimeoutError(
            "Timed out waiting for response cmd=0x{0:02X}".format(expected_cmd)
        )

    @staticmethod
    def _i16(value):
        return struct.pack("<h", int(value))

    @staticmethod
    def _u16(value):
        return struct.pack("<H", int(value) & 0xFFFF)

    @staticmethod
    def _u32(value):
        return struct.pack("<I", int(value) & 0xFFFFFFFF)

    @staticmethod
    def _i32(value):
        return struct.pack("<i", int(value))

    @staticmethod
    def _u8(value):
        return struct.pack("<B", int(value) & 0xFF)

    @staticmethod
    def _i8(value):
        return struct.pack("<b", int(value))

    @staticmethod
    def _parse_i16_at(payload, offset):
        return struct.unpack_from("<h", payload, offset)[0]

    def get_firmware_version(self, timeout=0.5):
        packet = self.request(
            SYSTEM_ID,
            NexArmCommand.CMD_FIRMWARE_VERSION_CHECK,
            expect_reply=True,
            expected_cmd=NexArmCommand.CMD_FIRMWARE_VERSION_CHECK,
            expected_ids=(SYSTEM_ID, 0x5A),
            timeout=timeout,
        )
        if len(packet.payload) < 3:
            raise ValueError("Firmware version response too short")
        major = packet.payload[0]
        minor = packet.payload[1]
        patch = packet.payload[2]
        return "{0}.{1}.{2}".format(major, minor, patch)

    def get_battery_voltage(self, timeout=0.5):
        packet = self.request(
            SYSTEM_ID,
            NexArmCommand.CMD_CHECK_BAT_LEVEL_CHECK,
            expect_reply=True,
            expected_cmd=NexArmCommand.CMD_CHECK_BAT_LEVEL_CHECK,
            expected_ids=(SYSTEM_ID, 0x5A),
            timeout=timeout,
        )
        if len(packet.payload) < 2:
            raise ValueError("Battery response too short")
        return struct.unpack_from("<H", packet.payload, 0)[0]

    def set_buzzer(self, on_ms, off_ms, times, frequency):
        payload = (
            self._u32(on_ms)
            + self._u32(off_ms)
            + self._u16(times)
            + self._u16(frequency)
        )
        self.request(SYSTEM_ID, NexArmCommand.CMD_BUZZER_SET, payload, expect_reply=False)

    def set_pose(self, x, y, z, pitch, roll, claw, duration_ms):
        payload = (
            self._i16(round(pitch * 10.0))
            + self._i16(round(x))
            + self._i16(round(y))
            + self._i16(round(z))
            + self._i16(round(roll))
            + self._i16(round(claw))
            + self._u16(duration_ms)
        )
        self.request(SYSTEM_ID, NexArmCommand.CMD_COORDINATE_SET, payload, expect_reply=False)

    def get_current_coords(self, timeout=0.5):
        packet = self.request(
            SYSTEM_ID,
            NexArmCommand.CMD_GET_CUR_COORDS,
            expect_reply=True,
            expected_cmd=NexArmCommand.CMD_GET_CUR_COORDS,
            expected_ids=(0x5A, SYSTEM_ID),
            timeout=timeout,
        )
        payload = packet.payload
        if len(payload) < 6:
            raise ValueError("Coordinate response too short")

        x = self._parse_i16_at(payload, 0)
        y = self._parse_i16_at(payload, 2)
        z = self._parse_i16_at(payload, 4)

        pitch = None
        roll = None
        claw = None
        servo_positions = ()

        if len(payload) >= 12:
            pitch = self._parse_i16_at(payload, 6) / 10.0
            roll = self._parse_i16_at(payload, 8)
            claw = self._parse_i16_at(payload, 10)

        if len(payload) >= 24:
            servo_positions = tuple(
                self._parse_i16_at(payload, 12 + i * 2) for i in range(6)
            )

        return NexArmCurrentCoords(
            x=x,
            y=y,
            z=z,
            pitch=pitch,
            roll=roll,
            claw=claw,
            servo_positions=servo_positions,
        )

    def move_increment(self, dx, dy, dz, dpitch, droll, dclaw, duration_ms):
        payload = (
            self._i16(round(dx))
            + self._i16(round(dy))
            + self._i16(round(dz))
            + self._i16(round(dpitch * 10.0))
            + self._i16(round(droll))
            + self._i16(round(dclaw))
            + self._u16(duration_ms)
        )
        self.request(SYSTEM_ID, NexArmCommand.CMD_ARM_MOVE_INC, payload, expect_reply=False)

    def set_espnow_sync(self, enabled):
        self.request(
            SYSTEM_ID,
            NexArmCommand.CMD_ESPNOW_SYNC_CTRL,
            self._u8(1 if enabled else 0),
            expect_reply=False,
        )

    def set_global_acceleration(self, accel):
        self.request(
            SYSTEM_ID,
            NexArmCommand.CMD_SET_GLOBAL_ACC,
            self._u8(accel),
            expect_reply=False,
        )

    def set_espnow_channel(self, channel):
        self.request(
            SYSTEM_ID,
            NexArmCommand.CMD_SET_ESPNOW_CHANNEL,
            self._u8(channel),
            expect_reply=False,
        )

    def mecanum_control(self, vx, vy, vz):
        payload = self._i8(vx) + self._i8(vy) + self._i8(vz)
        self.request(
            SYSTEM_ID,
            NexArmCommand.CMD_MECANUM_CONTROL,
            payload,
            expect_reply=False,
        )

    def stepper_control(self, step):
        self.request(
            SYSTEM_ID,
            NexArmCommand.CMD_STEPPER_RUN,
            self._i32(step),
            expect_reply=False,
        )

    def run_action_group(self, index):
        self.request(
            SYSTEM_ID,
            NexArmCommand.CMD_ACTION_GROUP_RUN,
            self._u8(index),
            expect_reply=False,
        )

    def stop_action_group(self):
        self.request(SYSTEM_ID, NexArmCommand.CMD_ACTION_GROUP_STOP, expect_reply=False)

    def erase_action_group(self, index):
        self.request(
            SYSTEM_ID,
            NexArmCommand.CMD_ACTION_GROUP_ERASE,
            self._u8(index),
            expect_reply=False,
        )

    @staticmethod
    def _validate_servo_id(servo_id):
        if not 1 <= servo_id <= 6:
            raise ValueError("servo_id must be in range 1..6")

    def servo_set_torque(self, servo_id, enable):
        self._validate_servo_id(servo_id)
        payload = self._u8(ServoRegister.TORQUE) + self._u8(1 if enable else 0)
        self.request(servo_id, ServoRegister.WRITE, payload, expect_reply=False)

    def servo_set_acceleration(self, servo_id, accel):
        self._validate_servo_id(servo_id)
        payload = self._u8(ServoRegister.ACC) + self._u8(accel)
        self.request(servo_id, ServoRegister.WRITE, payload, expect_reply=False)

    def servo_set_position(self, servo_id, position):
        self._validate_servo_id(servo_id)
        payload = self._u8(ServoRegister.POS) + self._u16(position)
        self.request(servo_id, ServoRegister.WRITE, payload, expect_reply=False)

    def servo_set_speed(self, servo_id, speed):
        self._validate_servo_id(servo_id)
        payload = self._u8(ServoRegister.SPEED) + self._u16(speed)
        self.request(servo_id, ServoRegister.WRITE, payload, expect_reply=False)

    def servo_write_acc_pos_speed(self, servo_id, accel, position, speed):
        self._validate_servo_id(servo_id)
        payload = (
            self._u8(ServoRegister.ACC)
            + self._u8(accel)
            + self._u16(position)
            + self._u16(0)
            + self._u16(speed)
        )
        self.request(servo_id, ServoRegister.WRITE, payload, expect_reply=False)
