"""A small bundled list of MAC vendor prefixes (OUI, the first 3 bytes of a
MAC address) of common home-network device makers.

Only the 3-byte prefix is stored, never a full MAC address, so the privacy
guard allows it. The list is short on purpose: a prefix that is missing gives
"unknown vendor", and a vendor says what a device probably is, not what it is
(a router maker also sells other things, a phone maker sells TVs). The report
always says "probably". Extend the list by adding prefixes from the IEEE
registry (https://standards-oui.ieee.org/oui/oui.txt); the lookup test checks
the format.

Format: vendor name -> (kind, prefixes). The kind is a key of oui.KIND_TEXT.
Prefixes are 6 hex digits separated by spaces.
"""

VENDORS = {
    "Apple": ("mobile", """
        001CB3 3C0754 A45E60 F01898 28CFE9 B8E856 0017F2 001B63 002500 0026BB
        ACBC32 D0034B"""),
    "Samsung": ("consumer", """
        001247 001599 001632 0017C9 001D25 002119 5C0A5B E8508B 8C7712 78471D"""),
    "Google (Nest, Chromecast)": ("media", """
        3C5AB4 F4F5D8 540609 A47733 1CF29A D86C63 30FD38"""),
    "Amazon (Echo, Fire TV, Ring)": ("media", """
        44650D 6854FD 74C246 FCA667 40B4CD 0C47C9 34D270 50DCE7 84D6D0 F0272D
        18742E"""),
    "Sonos": ("media", """
        000E58 347E5C 48A6B8 5CAAFD 7828CA B8E937 949F3E"""),
    "Raspberry Pi": ("board", """
        B827EB DCA632 E45F01 D83ADD 28CDC1 2CCF67"""),
    "Espressif (smart-home chips)": ("iot", """
        240AC4 246F28 30AEA4 3C71BF 5CCF7F 600194 68C63A 7C9EBD 840D8E 84F3EB
        8CAAB5 A020A6 A4CF12 AC67B2 B4E62D BCDDC2 C44F33 CC50E3 D8A01D DC4F22
        ECFABC 18FE34 2C3AE8 4C11AE 500291 545AA6"""),
    "Xiaomi": ("iot", """
        04CF8C 286C07 34CE00 50642B 640980 64B473 7811DC 7C49EB 8CBEBE 98FAE3
        F0B429 F8A45F 742344 584498"""),
    "Philips Hue (Signify)": ("lighting", """
        001788 ECB5FA"""),
    "TP-Link": ("router", """
        14CC20 18A6F7 1C3BF3 50C7BF 54C80F 60E327 647002 74DA88 98DAC4 A0F3C1
        B04E26 C04A00 D807B6 E894F6 EC086B F4F26D 30B5C2 8416F9 90F652 AC84C6
        98254A"""),
    "Netgear": ("router", """
        00095B 000FB5 00146C 00184D 001B2F 001E2A 001F33 00223F 0024B2 0026F2
        204E7F 28C68E 2CB05D 4494FC A021B7 A06391 C03F0E E0469A 9C3DCF"""),
    "D-Link": ("router", """
        00055D 000D88 000F3D 001195 001346 0015E9 00179A 00195B 001B11 001CF0
        001E58 002191 0022B0 002401 00265A 14D64D 1C7EE5 28107B 78542E 9094E4
        B8A386 C8BE19 CCB255 F07D68"""),
    "ASUS": ("router", """
        000C6E 000EA6 00112F 0013D4 0015F2 001731 0018F3 001A92 001BFC 001D60
        001E8C 001FC6 002215 002354 00248C 002618 04D4C4 08606E 10BF48 1C872C
        2C56DC 305A3A 382C4A 50465D 5404A6 74D02B AC220B BCEE7B F46D04"""),
    "AVM (Fritz!Box)": ("router", """
        00040E 00150C 001A4F 001C4A 001F3F 0024FE 0896D7 246511 2C3AFD 3810D5
        3CA62F 5C4979 7CFF4D 989BCB C02506 CCCE1E DC15C8 E8DF70"""),
    "Ubiquiti": ("router", """
        00156D 002722 0418D6 24A43C 44D9E7 687251 7483C2 788A20 802AA8 B4FBE4
        DC9FDB E063DA F09FC2 FCECDA"""),
    "MikroTik": ("router", """
        000C42 4C5E0C 64D154 6C3B6B 744D28 B869F4 CC2DE0 D4CA6D E48D8C"""),
    "Linksys (Cisco)": ("router", """
        000625 000C41 000F66 001217 001310 0014BF 0016B6 001839 0018F8 001A70
        001C10 001D7E 001EE5 002129 00226B 002369 00259C 20AA4B 586D8F C0C1C0"""),
    "Huawei": ("router", """
        00E0FC 04BD70 0819A6 104780 20F3A3 286ED4 4C5499 548998 5C7D5E 70723C
        78F557 80FB06 8853D4 9C28EF ACE215 C8D15E E0247F F4C714 FC48EF"""),
    "ZTE": ("router", """
        0015EB 0019C6 001E73 002293 002512 0026ED 344B50 4C09B4 8CE081 986CF5
        C87B5B"""),
    "Hikvision": ("camera", """
        1868CB 2857BE 4419B6 4CBD8F 54C415 5803FB 5C345B 80F503 8CE748 A41437
        BCAD28 C056E3 C42F90 E8A0ED F84DFC"""),
    "Dahua": ("camera", """
        3CEF8C 4C11BF 9002A9 9C1463 A0BD1D BC325F"""),
    "Axis Communications": ("camera", """
        00408C ACCC8E B8A44F E82725"""),
    "Canon": ("printer", """
        000085 001E8F 180CAC 2C9EFC F48139"""),
    "Brother": ("printer", """
        008077 001BA9 30055C"""),
    "Epson": ("printer", """
        000048 0026AB 389D92 44D244 64EB8C 9CAED3"""),
    "Lexmark": ("printer", """
        000400 002000 0021B7"""),
    "Xerox": ("printer", """
        0000AA"""),
    "Synology": ("nas", """
        001132 9009D0"""),
    "QNAP": ("nas", """
        00089B 245EBE"""),
    "Sony Interactive Entertainment (PlayStation)": ("console", """
        00041F 0015C1 0019C5 001D0D 001FA7 00248D 00D9D1 280DFC 709E29 A8E3EE
        BC60A7 F8461C FC0FE6"""),
    "Nintendo": ("console", """
        0009BF 001656 0017AB 00191D 0019FD 001AE9 001B7A 001BEA 001CBE 001E35
        001F32 002147 0022AA 0023CC 00241E 0025A0 182A7B 2C10C1 34AF2C 40D28A
        582F40 7CBB8A 98B6E9 9CE635 A4C0E1 B8AE6E CC9E00 D86BF7 E00C7F E84ECE"""),
    "Microsoft": ("computer", """
        0050F2 0003FF 000D3A 00125A 0017FA 001DD8 002248 0025AE 281878 6045BD
        7C1E52 7CED8D 985FD3"""),
    "Microsoft (Hyper-V virtual machine)": ("vm", """
        00155D"""),
    "LG Electronics": ("consumer", """
        001C62 001E75 001F6B 001FE3 0022A9 002483 0026E2 10683F 14C913 2021A5
        2C54CF 34FCEF 3CBDD8 40B0FA 58A2B5 64995D 6CD032 7440BE 785DC8 88C9D0
        A816B2 A823FE ACF108"""),
    "Intel (network card)": ("computer", """
        001B21 001E64 001F3B 00216A 0022FA 002314 0024D7 0026C6 3CA9F4 4851B7
        5CC5D4 8086F2 A44E31 AC7BA1 B46BFC"""),
    "VMware (virtual machine)": ("vm", """
        000C29 005056 000569"""),
    "Oracle VirtualBox (virtual machine)": ("vm", """
        080027"""),
}
