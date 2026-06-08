from __future__ import annotations

IDEMPOTENCY_MARKER = "# ks-gen unattended entry — do not edit"

ISOLINUX_UNATTENDED_ENTRY = """\
{marker}
label ksgen-unattended
  menu label ^Unattended STIG install (ks-gen)
  menu default
  kernel vmlinuz
  append initrd=initrd.img inst.stage2=hd:LABEL={volid} inst.ks=hd:LABEL={volid}:/ks.cfg quiet
"""

GRUB_UNATTENDED_ENTRY = (
    "{marker}\n"
    "menuentry 'Unattended STIG install (ks-gen)' "
    "--class fedora --class gnu-linux --class gnu --class os {{\n"
    "  linuxefi /images/pxeboot/vmlinuz "
    "inst.stage2=hd:LABEL={volid} inst.ks=hd:LABEL={volid}:/ks.cfg quiet\n"
    "  initrdefi /images/pxeboot/initrd.img\n"
    "}}\n"
)
