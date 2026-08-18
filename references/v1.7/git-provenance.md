# Git Provenance

Selected source evidence can carry:

- repository HEAD commit;
- HEAD blob SHA;
- index blob SHA;
- working-tree blob SHA;
- dirty/status state;
- content identity selecting HEAD or working tree.

This distinguishes two workers that mention the same path but analyzed different content versions. Symbol provenance additionally keeps symbol name, span and symbol fingerprint.

When Git is unavailable the capability degrades explicitly with `git_available=false`; it does not invent a commit identity.
