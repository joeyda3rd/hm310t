# Releasing hm310t

Releases are published by the tag-driven GitHub Actions workflow in
`.github/workflows/release.yml`. It reruns the hardware-free quality checks,
builds the sdist and wheel, publishes those exact artifacts to PyPI, then creates
or updates the matching GitHub release with the same files.

## One-time PyPI setup

Configure a PyPI trusted publisher for the existing `hm310t` project. In the
PyPI project's Publishing settings, register:

- Owner: `joeyda3rd`
- Repository: `hm310t`
- Workflow: `release.yml`
- Environment: `pypi`

The workflow uses GitHub's OpenID Connect token; it does not require a stored
PyPI API token. Create the GitHub `pypi` environment if it does not already
exist, and add any desired approval protection there. The workflow will wait at
the PyPI publish job until required environment approval is given.

## Release procedure

1. Update `pyproject.toml` and `CHANGELOG.md` to the intended version.
2. Run the normal checks locally.
3. Commit the release changes and push `main`.
4. Create and push the matching annotated tag. For this release:

   ```bash
   git tag -a v0.1.3 -m "chore: release 0.1.3"
   git push origin v0.1.3
   ```

5. Monitor the Release workflow. After the verification job, approve the `pypi`
   environment if it is protected. Confirm the PyPI project and GitHub release
   both show version 0.1.3.

To retry a completed tag, run the Release workflow manually and provide that
existing tag. The workflow checks that the tag matches `project.version`, does
not upload before verification succeeds, and updates GitHub release artifacts on
retry. PyPI rejects attempts to replace an already-published distribution, so a
failed publish after a partial upload should be investigated rather than retried
unchanged.
