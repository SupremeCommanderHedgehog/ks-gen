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
    "  linuxefi /images/pxeboot/vmlinuz"
    " inst.stage2=hd:LABEL={volid}"
    "{repo}"
    " inst.ks=hd:LABEL={volid}:/ks.cfg"
    " quiet\n"
    "  initrdefi /images/pxeboot/initrd.img\n"
    "}}\n"
)
