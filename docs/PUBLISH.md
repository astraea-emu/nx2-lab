# Publish the repository with preserved history

The project is a local Git repository and has not been published to GitHub.
The connected GitHub app can manage an existing repository but currently
cannot create a new one. Do not publish under the Astraea repository or erase
its history.

1. At https://github.com/new create an **empty** repository named `nx2-lab`
   in the account that will own the project. Do not pre-populate with a README,
   license, or .gitignore; these are already in the history.
2. From the original local project repository (which has no remote), add
   the remote and push:

```sh
git remote add origin https://github.com/OWNER/nx2-lab.git
git push --set-upstream origin main
```

To restore from the supplied `nx2-lab.bundle` on a new machine, **replace**
(the bundle clone's already-existing `origin` points at the local bundle):

```sh
git clone nx2-lab-20261029.bundle nx2-lab
cd nx2-lab
git remote set-url origin https://github.com/OWNER/nx2-lab.git
git push --set-upstream origin main
``` To verify source code
without Git history, the standalone source ZIP contains only tracked files.

After publishing, enable protected main, require build/test CI and reviews as
appropriate. Do not publish firmware, console captures, copyrighted binaries,
keys, or host configuration secrets.
