from __future__ import annotations

IDEMPOTENCY_MARKER = "# ks-gen unattended entry — do not edit"

ISOLINUX_UNATTENDED_ENTRY = (
    "{marker}\n"
    "label ksgen-unattended\n"
    "  menu label ^Unattended STIG install (ks-gen)\n"
    "  menu default\n"
    "  kernel vmlinuz\n"
    "  append initrd=initrd.img"
    " inst.stage2=hd:LABEL={volid}"
    "{repo}"
    " inst.ks=hd:LABEL={volid}:/ks.cfg"
    " quiet\n"
)

GRUB_UNATTENDED_ENTRY = (
    "{marker}\n"
    "menuentry 'Unattended STIG install (ks-gen)' "
    "--class fedora --class gnu-linux --class gnu --class os {{\n"
    "  {linux} /images/pxeboot/vmlinuz"
    " inst.stage2=hd:LABEL={volid}"
    "{repo}"
    " inst.ks=hd:LABEL={volid}:/ks.cfg"
    " quiet\n"
    "  {initrd} /images/pxeboot/initrd.img\n"
    "}}\n"
)

# The i386-pc grub build used for BIOS boot has no linuxefi/initrdefi.
GRUB_EFI_LOADER = {"linux": "linuxefi", "initrd": "initrdefi"}
GRUB_BIOS_LOADER = {"linux": "linux", "initrd": "initrd"}
