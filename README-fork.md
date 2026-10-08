# Personal SiYuan fork

This fork enables local paid features and S3, WebDAV, and local filesystem sync without an official cloud account. It does not create a synthetic VIP user; official SiYuan Cloud still requires its real account and subscription. The explicit switches live in `kernel/conf/fork.go` and `app/src/util/fork.ts`. Preserve both switches when rebasing. Existing workspace keys, encrypted notebook formats, and configured sync providers are preserved. Fresh workspaces default to WebDAV with conflict documents enabled; synchronization remains off until configured.

Official version checks, cached installer execution, and installer downloads are disabled in the kernel, including when an existing workspace has automatic downloads enabled. Install fork updates manually. The upstream update settings remain visible but do not enable the upstream updater. No tray, iOS signing, or fake cloud-account patches are included. Android builds use independent fork signing as described below.

## AppImages

Run **Fork AppImages** from GitHub Actions for native x64 and ARM64 builds. It uses the checked-out fork source, the Go version from `kernel/go.mod`, Node 24, and the pnpm version from `app/package.json`. No upstream signing secrets or Android build are required. Download the two workflow artifacts; each contains an AppImage, corresponding source archive, and SHA-256 checksum file. Extract them and run `sha256sum --check SHA256SUMS-x64.txt` or the ARM64 equivalent, then make the AppImage executable with `chmod +x <filename>.AppImage`.

Pushing a tag named `fork-v<app/package.json version>` also creates a draft GitHub release after both architectures pass. Publish the draft after review. The workflow uses only `GITHUB_TOKEN`; enable GitHub Actions for the fork. Release jobs have permission to write repository contents. Manual runs produce downloadable artifacts without creating a release. The inherited upstream workflows are separate and may still require upstream platform secrets; use **Fork AppImages** for this deployment.

The fork retains `LICENSE` and `THIRD_PARTY_NOTICES.md` in packaged applications and includes the corresponding fork source with its artifacts. Keep these files and source availability when distributing or serving modified software.

## Android APKs

Run **Fork APKs** in **Actions - Fork APKs - Run workflow** after the workflow has been committed and pushed. Select `debug` for a test APK without signing secrets, or `release` for an optimized APK signed with your own persistent key. Manual runs upload artifacts without publishing a release. The workflow builds this fork's mobile and export frontends and ARM64 kernel, uses Java 21, and pins the Android wrapper to the upstream 3.8.6 commit. Android 8.0 or later on an ARM64 device is required. When upgrading the fork, review and update `ANDROID_REF` in `.github/workflows/fork-apk.yml`; the build rejects a wrapper whose version differs from `app/package.json`.

Download `siyuan-fork-android-arm64-debug` or `siyuan-fork-android-arm64-release`, extract it, and run `sha256sum --check SHA256SUMS-android.txt`. The artifact contains the APK, both corresponding source archives (including the Android fork adjustments), checksums, and build commit information. Transfer the APK to your phone and allow installation from the app used to open it. The release package is `org.b3log.siyuan.fork`; debug is `org.b3log.siyuan.fork.debug`. Both can coexist with official SiYuan and use separate app storage. Configure sync using the existing data repo key; neither variant imports another installation's workspace automatically.

For APKs that can update an existing installation, create and securely back up a private keystore once. For example:

```sh
keytool -genkeypair -keystore siyuan-fork.jks -alias siyuan-fork -keyalg RSA -keysize 3072 -validity 10000
```

Configure these repository secrets in **Settings - Secrets and variables - Actions**:

- `FORK_ANDROID_KEYSTORE_BASE64`: the keystore encoded as base64
- `FORK_ANDROID_KEYSTORE_PASSWORD`: the keystore password
- `FORK_ANDROID_KEY_ALIAS`: `siyuan-fork` if using the example
- `FORK_ANDROID_KEY_PASSWORD`: the private key password

All four secrets must be supplied together. Release builds require them; debug builds also use them when configured. Keep the keystore and passwords in independent secure storage and reuse the same key for every update. The workflow reads credentials from the environment, excludes the keystore from artifacts, verifies the APK signature, and removes the runner's keystore afterward. No upstream signing secrets are used.

Without these secrets, debug builds use a temporary runner certificate that changes between runs. These APKs are for testing and cannot reliably update one another in place. Back up the workspace and recovery keys before replacing such an installation; uninstalling Android apps removes their private data. Use persistent signing from the first installation intended for ongoing use. Debug and release variants have separate package IDs even when signed with the same key.

## Sync and backup server

The deployment provides authenticated S3-compatible storage using [SeaweedFS](https://github.com/seaweedfs/seaweedfs/wiki/Quick-Start-with-weed-mini). It uses SiYuan's third-party sync protocol and does not run a second SiYuan kernel or emulate the official cloud API. The Compose stack and Borg tools are in `deploy/sync/`.

On a Linux server with Docker Compose and Python 3, copy `deploy/sync/` to `/opt/siyuan-sync`, then:

```sh
cd /opt/siyuan-sync
python3 setup.py
docker compose up -d s3
```

Setup generates independent S3 credentials and a Borg password, stores them in a private `secrets/` directory, and refuses to overwrite existing credentials or initialize over existing S3 state. It creates `.env` from `.env.example` and sets the service UID/GID to the owner of the credentials, so the unprivileged service can read its private files. Preserve these IDs or adjust file ownership when moving to another host. Keep an independent, secure copy of `secrets/borg-passphrase` before backing up. Never delete or regenerate existing credentials to fix an authentication error.

The S3 service listens on `127.0.0.1:8333` by default; set `SYNC_BIND_ADDRESS` in `.env` to the server's private Tailscale/VPN IPv4 address for access from other devices, then run `docker compose up -d s3`. Only the authenticated S3 port is published; management interfaces remain unpublished. Use HTTPS outside an encrypted tunnel. SeaweedFS is pinned to version 4.48; its complete persistent state is stored in `s3-data/`. Preserve this directory and `secrets/s3.json` together for recovery.

In each fork client, open **Settings - Account & Sync**, choose S3, and set the endpoint to `http://<server-vpn-ip>:8333`, bucket to `siyuan`, region to `us-east-1`, and enable path-style access. Read the `accessKey` and `secretKey` from `secrets/s3.json` privately. These authenticate storage access; they are separate from SiYuan's data repo encryption key. Import the same exported data repo key on all devices instead of generating independent keys. Sync the first client successfully before connecting the second. Workspace names and paths are local to each device; synchronized notebooks and notes should appear in both workspaces.

For a legacy WebDAV deployment, run `python3 setup_s3.py` once to add S3 credentials without changing existing credentials. Back up each workspace, retain the existing repo key, and upload the first client's current notes to S3 before configuring other clients. After all clients successfully sync with S3, run `docker compose up -d --remove-orphans s3` to remove the retired WebDAV container. Keep `data/` and legacy credentials for recovery; the backup still includes them, but no WebDAV service or port remains active. Changing providers does not decrypt an old repository with a different key.

Privately export the working client's data repo key to `secrets/data-repo-key.txt` with permissions `0600` so the encrypted Borg archive includes the material needed to decrypt synchronized notes. Do not overwrite an existing recovery key without verifying it against the current repository. Keep notebook passwords and encrypted-notebook recovery material separately. Official upstream clients may still enforce their own subscription checks; use clients built from this fork, including mobile builds if needed.

## Borg backups and restore

Run a consistent backup with:

```sh
cd /opt/siyuan-sync
python3 backup.py
```

The host helper serializes backups, builds the Borg tool image before stopping sync, stops a running S3 service, archives its complete persistent state and deployment configuration including credentials and saved recovery keys, then restarts a previously running service even if backup fails. A service that was already stopped stays stopped. The backup container has no Docker socket access. Ordinary failures and termination signals trigger cleanup; an uncatchable kill or host failure can leave sync stopped, so check `docker compose ps` and restart it after recovery. Archives use Borg 1.x repokey encryption and deduplication. Creation must succeed before pruning; retention is 7 daily, 4 weekly, and 12 monthly archives, followed by compaction. Authentication failures or damaged repositories cause an error without reinitialization. See [Borg's retention documentation](https://borgbackup.readthedocs.io/en/1.4.0/usage/prune.html).

The default repository is `borg/repository`. Set `BORG_DIRECTORY` in `.env` to an absolute directory on a separate backup disk, outside the deployment directory, for production. Copy the Borg repository and exported key off-host as well; a second directory on the same disk cannot recover from losing that disk. Credentials and cached security state are sensitive; preserve restrictive host permissions.

Export the encryption key after the first successful backup and copy it, with the passphrase, into independent secure storage:

```sh
docker compose run --rm --no-deps backup key export /borg/repository /borg/recovery-key
docker compose run --rm --no-deps backup list
docker compose run --rm --no-deps backup check --verify-data
```

Extract a selected archive into the separate `restore/` directory for review:

```sh
docker compose run --rm --no-deps --workdir /restore backup extract ::ARCHIVE_NAME
```

New archives contain `data/` (retained legacy WebDAV repositories), `s3-data/` (complete S3 server state), and `deployment/` (configuration, scripts, credentials, and saved recovery keys). Existing WebDAV-only archives remain recoverable and have no `s3-data/` directory. Archives exclude the backup repository, cache, restore directory, and duplicate data mounts. Review the extracted data before replacing anything. Stop S3, move the current `s3-data/` directory aside, copy `restore/s3-data/` into its place, restore the reviewed configuration and credentials if necessary, and start S3 again. Keep the old directory until the restored service and clients are verified. Preserve or restore legacy `data/` separately. For a WebDAV-only archive, use its archived Compose configuration in a separate recovery deployment and leave existing S3 state untouched. On a new host, recover the separately saved passphrase and Borg repository first; do not run setup over restored secrets. The exported key supports Borg's `key import` recovery if repository key material is lost.

This backs up the complete sync server. A sync repository is not a complete desktop workspace: unsynced edits, local history, device settings, plugins, and local-only files can be absent. For full desktop recovery, also back up the entire workspace after exiting SiYuan, including configuration and key/recovery material. This task does not modify the encrypted notebook or sync storage formats.

To schedule daily backups at 03:00 server time with a small randomized delay, copy `systemd/siyuan-sync-backup.service` and `.timer` into `/etc/systemd/system/`, adjusting `/opt/siyuan-sync` if necessary, then:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now siyuan-sync-backup.timer
systemctl list-timers siyuan-sync-backup.timer
journalctl -u siyuan-sync-backup.service
```

The system service runs as root so it can control Docker and read server data. For a user service, place both files in `~/.config/systemd/user/`, remove the system Docker `Requires` and `After` lines, adjust deployment paths, and use `systemctl --user` instead. The user must have Docker access. Enable lingering with `loginctl enable-linger <username>` to keep user timers active after logout; otherwise they run only while the user manager is active. Monitor failed units and regularly test extraction. The timer is on the host so no container needs privileged Docker access.

## Verification

Frontend: `pnpm run lint` and `pnpm exec tsx --test src/util/needSubscribe.test.ts src/config/tabs/syncUi.test.ts src/config/tabs/syncRuntime.test.ts` from `app/`. Kernel: `go test -tags 'fts5 sqlcipher' ./conf ./model -run 'Test(SelfHosted|CheckSync|ForkUpdater)'` from `kernel/`. Deployment integration: `python3 scripts/test_sync_deployment.py` from the repository root; it creates and removes an isolated temporary Compose project, tests signed S3 operations, rejects invalid credentials and credential regeneration over existing state, creates and restores a Borg archive including S3 state, legacy data, credentials, and saved recovery keys, and verifies service recovery after repository corruption while preserving an initially stopped service.
