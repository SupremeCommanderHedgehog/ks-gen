"""alma8 kernel_module_blacklist — re-exports the alma9 implementation.

/etc/modprobe.d/ and the modprobe install-trick (install <m> /bin/true)
are universal. The alma9 default module list (usb-storage, cramfs,
freevxfs, jffs2, hfs, hfsplus, squashfs, udf) targets filesystems and
removable-media drivers that are equally present-or-absent on the
4.18 (AL8) and 5.14 (AL9) kernels — the install-trick is a harmless
no-op for any module that isn't present.
"""

from __future__ import annotations

from ks_gen.rules.alma9.kernel_module_blacklist import RULE

__all__ = ["RULE"]
