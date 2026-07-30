from pathlib import Path
import re

root = Path(r"D:/diansai/2026/firmware/stm32f103ve_uart_magnet")
base = (root / "firmware.uvprojx").read_text(encoding="utf-8")

replacements_common = [
    ("<Device>STM32F103C8</Device>", "<Device>STM32F103VE</Device>"),
    (
        'IROM(0x08000000,0x10000) IRAM(0x20000000,0x5000) CPUTYPE("Cortex-M3") CLOCK(12000000) ELITTLE',
        'IROM(0x08000000,0x80000) IRAM(0x20000000,0x10000) CPUTYPE("Cortex-M3") CLOCK(12000000) ELITTLE',
    ),
    ("FF0STM32F10x_128", "FF0STM32F10x_512"),
    ("-FL020000", "-FL080000"),
    ("STM32F10x_128.FLM", "STM32F10x_512.FLM"),
    ("$$Device:STM32F103C8$", "$$Device:STM32F103VE$"),
    ("startup_stm32f10x_md.s", "startup_stm32f10x_hd.s"),
]


def make(name: str, outname: str, define: str, include_magnet: bool) -> str:
    t = base
    for a, b in replacements_common:
        t = t.replace(a, b)
    t = t.replace(
        "<TargetName>STM32F103_UART_MAGNET</TargetName>",
        f"<TargetName>{name}</TargetName>",
    )
    t = t.replace(
        "<OutputName>firmware</OutputName>",
        f"<OutputName>{outname}</OutputName>",
    )
    t = t.replace("<Define>STM32F10X_MD</Define>", f"<Define>{define}</Define>")
    t = re.sub(
        r"(<IRAM>\s*<Type>0</Type>\s*<StartAddress>0x20000000</StartAddress>\s*<Size>)0x5000(</Size>)",
        r"\g<1>0x10000\g<2>",
        t,
    )
    t = re.sub(
        r"(<IROM>\s*<Type>1</Type>\s*<StartAddress>0x8000000</StartAddress>\s*<Size>)0x10000(</Size>)",
        r"\g<1>0x80000\g<2>",
        t,
    )
    t = re.sub(
        r"(<OCR_RVCT4>\s*<Type>1</Type>\s*<StartAddress>0x8000000</StartAddress>\s*<Size>)0x10000(</Size>)",
        r"\g<1>0x80000\g<2>",
        t,
    )
    t = re.sub(
        r"(<OCR_RVCT9>\s*<Type>0</Type>\s*<StartAddress>0x20000000</StartAddress>\s*<Size>)0x5000(</Size>)",
        r"\g<1>0x10000\g<2>",
        t,
    )
    if not include_magnet:
        t = re.sub(
            r"\s*<File>\s*<FileName>magnet_control\.c</FileName>.*?</File>",
            "",
            t,
            flags=re.S,
        )
        t = re.sub(
            r"\s*<File>\s*<FileName>magnet_control\.h</FileName>.*?</File>",
            "",
            t,
            flags=re.S,
        )
    insert = """            <File>
              <FileName>board_config.h</FileName>
              <FileType>5</FileType>
              <FilePath>.\\inc\\board_config.h</FilePath>
            </File>
"""
    t = t.replace(
        """            <File>
              <FileName>stm32f10x_conf.h</FileName>""",
        insert
        + """            <File>
              <FileName>stm32f10x_conf.h</FileName>""",
    )
    return t


(root / "ping.uvprojx").write_text(
    make("STM32F103VE_UART_PING", "stm32f103ve_uart_ping", "STM32F10X_HD,STAGE_PING", False),
    encoding="utf-8",
)
(root / "magnet.uvprojx").write_text(
    make("STM32F103VE_UART_MAGNET", "stm32f103ve_uart_magnet", "STM32F10X_HD", True),
    encoding="utf-8",
)
md = root / "startup" / "startup_stm32f10x_md.s"
if md.exists():
    md.unlink()
print("ok")
