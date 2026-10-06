# Personal SiYuan fork

This fork enables local paid features and S3, WebDAV, and local filesystem sync without an official cloud account. It does not create a synthetic VIP user; official SiYuan Cloud still requires its real account and subscription. The explicit switches live in `kernel/conf/fork.go` and `app/src/util/fork.ts`. Preserve both switches when rebasing. Existing workspace keys, encrypted notebook formats, and configured sync providers are preserved. Fresh workspaces default to WebDAV with conflict documents enabled; synchronization remains off until configured.

Official version checks, cached installer execution, and installer downloads are disabled in the kernel, including when an existing workspace has automatic downloads enabled. Install fork updates manually. The upstream update settings remain visible but do not enable the upstream updater. No tray, Android signing, iOS signing, or fake cloud-account patches are included.

## AppImages

Run **Fork AppImages** from GitHub Actions for native x64 and ARM64 builds. It uses the checked-out fork source, the Go version from `kernel/go.mod`, Node 24, and the pnpm version from `app/package.json`. No upstream signing secrets or Android build are required. Download the two workflow artifacts; each contains an AppImage, corresponding source archive, and SHA-256 checksum file. Extract them and run `sha256sum --check SHA256SUMS-x64.txt` or the ARM64 equivalent, then make the AppImage executable with `chmod +x <filename>.AppImage`.

Pushing a tag named `fork-v<app/package.json version>` also creates a draft GitHub release after both architectures pass. Publish the draft after review. The workflow uses only `GITHUB_TOKEN`; enable GitHub Actions for the fork. Release jobs have permission to write repository contents. Manual runs produce downloadable artifacts without creating a release. The inherited upstream workflows are separate and may still require upstream platform secrets; use **Fork AppImages** for this deployment.

The fork retains `LICENSE` and `THIRD_PARTY_NOTICES.md` in packaged applications and includes the corresponding fork source with its artifacts. Keep these files and source availability when distributing or serving modified software.

## Sync and backup server

The service is an authenticated WebDAV endpoint compatible with SiYuan's existing third-party sync protocol, using [rclone's WebDAV server](https://rclone.org/commands/rclone_serve_webdav/). It does not run a second SiYuan kernel or emulate the official cloud API. The Compose stack and Borg tools are in `deploy/sync/`.

On a Linux server with Docker Compose and Python 3, copy `deploy/sync/` to `/opt/siyuan-sync`, then:

```sh
cd /opt/siyuan-sync
python3 setup.py --username siyuan
docker compose up -d sync
```

Setup generates independent random WebDAV and Borg passwords, stores them in a private `secrets/` directory, and refuses to overwrite existing credentials. It creates `.env` from `.env.example` and sets the service UID/GID to the owner of the credentials, so the unprivileged service can read its private files. Preserve these IDs or adjust file ownership when moving to another host. Read `secrets/webdav-password` locally to configure your clients. Keep an independent, secure copy of `secrets/borg-passphrase` before backing up. Never delete or regenerate existing credentials to fix an authentication error.

The endpoint listens on `127.0.0.1:6807` by default. Connect through a VPN or an HTTPS reverse proxy on the server. Forward WebDAV methods, including `PROPFIND`, `MKCOL`, `PUT`, and `DELETE`, and allow sufficiently large request bodies. For a proxy running in Docker, attach it to the Compose network and target `sync:8080`; for a host proxy, target `127.0.0.1:6807`. Set `SYNC_BIND_ADDRESS` in `.env` to the server's private VPN address if clients connect directly through that VPN. Use HTTPS for access outside an encrypted tunnel.

In each fork client, open **Settings - Sync**, choose WebDAV, and enter the endpoint URL, username, and generated password. Keep TLS verification enabled. Configure the same sync directory and SiYuan data-repository encryption password on all devices, then enable sync. These credentials are distinct from the WebDAV password and the Borg passphrase. Preserve notebook passwords and recovery material separately. An official upstream client may still enforce its own subscription checks; use clients built from this fork, including mobile builds if you later add them.

## Borg backups and restore

Run a consistent backup with:

```sh
cd /opt/siyuan-sync
python3 backup.py
```

The host helper serializes backups, builds the Borg tool image before stopping sync, stops the WebDAV service, archives all server sync data and deployment configuration including credentials, then restarts a previously running service even if backup fails. A service that was already stopped stays stopped. The backup container has no Docker socket access. Ordinary failures and termination signals trigger cleanup; an uncatchable kill or host failure can leave sync stopped, so check `docker compose ps` and restart it after recovery. Archives use Borg 1.x repokey encryption and deduplication. Creation must succeed before pruning; retention is 7 daily, 4 weekly, and 12 monthly archives, followed by compaction. Authentication failures or damaged repositories cause an error without reinitialization. See [Borg's retention documentation](https://borgbackup.readthedocs.io/en/1.4.0/usage/prune.html).

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

The archive contains `data/` (all synchronized repository contents) and `deployment/` (configuration, scripts, and secrets). It excludes the backup repository, cache, restore directory, and duplicate data mount. Review the extracted data before replacing anything. Stop sync, move the current `data/` directory aside, copy the restored `restore/data/` into its place, restore the reviewed configuration and credentials if necessary, and start sync again. Keep the old directory until the restored service and clients are verified. On a new host, recover the separately saved passphrase and Borg repository first; do not run setup over restored secrets. The exported key supports Borg's `key import` recovery if repository key material is lost.

This backs up the complete sync server. A sync repository is not a complete desktop workspace: unsynced edits, local history, device settings, plugins, and local-only files can be absent. For full desktop recovery, also back up the entire workspace after exiting SiYuan, including configuration and key/recovery material. This task does not modify the encrypted notebook or sync storage formats.

To schedule daily backups at 03:00 server time with a small randomized delay, copy `systemd/siyuan-sync-backup.service` and `.timer` into `/etc/systemd/system/`, adjusting `/opt/siyuan-sync` if necessary, then:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now siyuan-sync-backup.timer
systemctl list-timers siyuan-sync-backup.timer
journalctl -u siyuan-sync-backup.service
```

The system service runs as root so it can control Docker and read server data. Monitor failed units and regularly test extraction. The timer is on the host so no container needs privileged Docker access.

## Verification

Frontend: `pnpm run lint` and `pnpm exec tsx --test src/util/needSubscribe.test.ts src/config/tabs/syncUi.test.ts src/config/tabs/syncRuntime.test.ts` from `app/`. Kernel: `go test -tags 'fts5 sqlcipher' ./conf ./model -run 'Test(SelfHosted|CheckSync|ForkUpdater)'` from `kernel/`. Deployment integration: `python3 scripts/test_sync_deployment.py` from the repository root; it creates and removes an isolated temporary Compose project, tests authentication and WebDAV operations, creates and restores a Borg archive, and verifies service recovery after repository corruption.
