"""Verify the build-debug-iso.py monkey-patch produces serial-bootable entries."""

from ks_gen.iso import bootloader

DEBUG_KERNEL_ARGS = (
    "inst.text inst.notmux inst.console=ttyS0,115200n8 console=ttyS0,115200n8"
)

print("Before patch:")
print("  ISOLINUX ends with ' quiet\\n':", bootloader.ISOLINUX_UNATTENDED_ENTRY.endswith(" quiet\n"))
print("  GRUB has ' quiet\\n':", " quiet\n" in bootloader.GRUB_UNATTENDED_ENTRY)
print()

bootloader.ISOLINUX_UNATTENDED_ENTRY = bootloader.ISOLINUX_UNATTENDED_ENTRY.replace(
    " quiet\n", f" {DEBUG_KERNEL_ARGS}\n"
)
bootloader.GRUB_UNATTENDED_ENTRY = bootloader.GRUB_UNATTENDED_ENTRY.replace(
    " quiet\n", f" {DEBUG_KERNEL_ARGS}\n"
)

print("After patch:")
print("  ISOLINUX has 'quiet\\n':", "quiet\n" in bootloader.ISOLINUX_UNATTENDED_ENTRY)
print("  GRUB has 'quiet\\n':", "quiet\n" in bootloader.GRUB_UNATTENDED_ENTRY)
print("  ISOLINUX has DEBUG args:", DEBUG_KERNEL_ARGS in bootloader.ISOLINUX_UNATTENDED_ENTRY)
print("  GRUB has DEBUG args:", DEBUG_KERNEL_ARGS in bootloader.GRUB_UNATTENDED_ENTRY)
print()
print("Patched GRUB entry:")
print(bootloader.GRUB_UNATTENDED_ENTRY)
print()
print("Patched ISOLINUX entry:")
print(bootloader.ISOLINUX_UNATTENDED_ENTRY)
print()

# Now simulate what build_iso does — render the bootloader files using the patched constants.
from ks_gen.iso.bootloader import render_grub_cfg, render_isolinux_cfg

print("Rendered grub.cfg (first 30 lines):")
grub = render_grub_cfg(volid="ALMA9")
for line in grub.splitlines()[:30]:
    print(" ", line)
print()
print("Rendered isolinux.cfg (first 30 lines):")
isolinux = render_isolinux_cfg(volid="ALMA9")
for line in isolinux.splitlines()[:30]:
    print(" ", line)
