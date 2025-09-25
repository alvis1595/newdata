# -*- coding: utf-8 -*-

from ansible.module_utils.basic import AnsibleModule
import shlex

DOCUMENTATION = r'''
---
module: rsync_sync
short_description: Sincroniza archivos vía rsync/ssh (push y pull, con soporte check_mode)
version_added: "1.1.0"
author: "alvis1595 (+ ChatGPT)"
description:
  - Ejecuta rsync sobre SSH usando sshpass (opcional) y opciones para (des)activar verificación de host.
  - Soporta modo push (local->remoto) y pull (remoto->local).
  - En check_mode ejecuta --dry-run para calcular 'changed' sin aplicar cambios.
options:
  mode:
    description: Dirección de sincronización (push o pull).
    required: false
    type: str
    choices: ['push', 'pull']
    default: 'push'
  src:
    description:
      - En push: ruta local a sincronizar (en el host donde se ejecuta el módulo).
      - En pull: ruta remota a sincronizar (en el host remoto origen).
    required: true
    type: str
  dest_host:
    description:
      - En push: host destino (nombre o IP).
      - En pull: host origen (del que se trae).
    required: true
    type: str
  dest_user:
    description:
      - Usuario SSH para el host indicado en dest_host.
    required: true
    type: str
  dest_path:
    description:
      - En push: ruta destino en el host remoto.
      - En pull: ruta destino local en el host que ejecuta el módulo.
    required: true
    type: str
  ssh_password:
    description: Contraseña SSH (usa sshpass). Si se omite, no se utilizará sshpass.
    required: false
    type: str
    no_log: true
  port:
    description: Puerto SSH.
    required: false
    type: int
    default: 22
  delete:
    description: Eliminar en destino lo que no existe en origen (rsync --delete).
    required: false
    type: bool
    default: false
  excludes:
    description: Lista de patrones a excluir (rsync --exclude).
    required: false
    type: list
    elements: str
    default: []
  strict_host_key_checking:
    description: Habilitar verificación estricta de host SSH.
    required: false
    type: bool
    default: false
  user_known_hosts_file:
    description: Ruta del known_hosts a usar. Si strict_host_key_checking=false, se recomienda /dev/null.
    required: false
    type: str
    default: "/dev/null"
  rsync_extra_opts:
    description: Lista de opciones adicionales para rsync.
    required: false
    type: list
    elements: str
    default: []
requirements:
  - rsync
  - sshpass (solo si se entrega ssh_password)
notes:
  - Considera usar llaves SSH en lugar de contraseñas por seguridad.
'''

EXAMPLES = r'''
# PUSH (local -> remoto)
- name: Subir /data/ del host actual al 10.0.0.20:/var/www/
  alvis1595.sincronizar.rsync_sync:
    mode: push
    src: /data/
    dest_host: 10.0.0.20
    dest_user: deploy
    dest_path: /var/www/
    ssh_password: "{{ password_remoto }}"
    strict_host_key_checking: false
    excludes:
      - "*.tmp"
      - ".git/"
    delete: false

# PULL (remoto -> local)   <-- NUEVO
- name: Traer /task/ desde 192.168.0.21 hacia ESTE host (destino local)
  alvis1595.sincronizar.rsync_sync:
    mode: pull
    src: /task/
    dest_host: 192.168.0.21
    dest_user: usuario21
    dest_path: /task/
    ssh_password: "{{ password_origen }}"
    strict_host_key_checking: false
'''

RETURN = r'''
cmd:
  description: Comando rsync ejecutado (sin credenciales).
  type: str
stdout:
  description: Salida estándar de rsync.
  type: str
stderr:
  description: Error estándar de rsync.
  type: str
files_transferred:
  description: Número de archivos con cambios/transferencias (estimado vía --itemize-changes).
  type: int
deleted:
  description: Número de elementos eliminados (cuando delete=true).
  type: int
changed:
  description: Si hubo (o habría) cambios.
  type: bool
'''

def build_ssh_cmd(port, strict, known_hosts_file):
    ssh_opts = [
        "-o", "ConnectTimeout=20",
        "-p", str(port),
    ]
    if not strict:
        ssh_opts += ["-o", "StrictHostKeyChecking=no"]
        ssh_opts += ["-o", f"UserKnownHostsFile={known_hosts_file or '/dev/null'}"]
    return ["ssh"] + ssh_opts

def count_changes_from_itemize(out_text):
    files = 0
    deleted = 0
    for line in out_text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("*deleting"):
            deleted += 1
        elif s[:1] in (">", "c"):  # ">" transfer/actualización, "c" cambios de metadata/crear
            files += 1
    return files, deleted

def run_rsync(module, dry_run=False):
    p = module.params
    ssh_cmd = build_ssh_cmd(p['port'], p['strict_host_key_checking'], p['user_known_hosts_file'])
    ssh_spec = " ".join(shlex.quote(x) for x in ssh_cmd)

    mode = p.get('mode', 'push')

    # PUSH: local -> remoto
    # PULL: remoto -> local
    if mode == 'push':
        rsync_src = p['src']  # local
        rsync_dest = f"{p['dest_user']}@{p['dest_host']}:{p['dest_path']}"  # remoto
    elif mode == 'pull':
        rsync_src = f"{p['dest_user']}@{p['dest_host']}:{p['src']}"  # remoto
        rsync_dest = p['dest_path']  # local
    else:
        module.fail_json(msg="mode debe ser 'push' o 'pull'")

    rsync_cmd = ["rsync", "--itemize-changes", "-avz", "-e", ssh_spec]

    if p['delete']:
        rsync_cmd.append("--delete")
    if dry_run:
        rsync_cmd.append("--dry-run")
    for pat in (p['excludes'] or []):
        rsync_cmd.extend(["--exclude", pat])
    for opt in (p['rsync_extra_opts'] or []):
        rsync_cmd.append(opt)

    rsync_cmd.extend([rsync_src, rsync_dest])

    cmd = rsync_cmd
    if p.get('ssh_password'):
        cmd = ["sshpass", "-p", p['ssh_password']] + rsync_cmd

    rc, out, err = module.run_command(cmd, use_unsafe_shell=False)

    # rc aceptables en rsync (0 ok, 23/24 partial-file/partial-transfer)
    if rc not in (0, 23, 24):
        module.fail_json(msg="Fallo al ejecutar rsync", rc=rc, stdout=out, stderr=err, cmd=" ".join(rsync_cmd))

    files, deleted = count_changes_from_itemize(out or "")
    changed = (files > 0) or (deleted > 0)

    return dict(
        cmd=" ".join(rsync_cmd),
        stdout=out,
        stderr=err,
        files_transferred=files,
        deleted=deleted,
        changed=changed,
        rc=rc,
    )

def main():
    module = AnsibleModule(
        argument_spec=dict(
            mode=dict(type='str', required=False, default='push', choices=['push','pull']),
            src=dict(type='str', required=True),
            dest_host=dict(type='str', required=True),
            dest_user=dict(type='str', required=True),
            dest_path=dict(type='str', required=True),
            ssh_password=dict(type='str', required=False, no_log=True, default=None),
            port=dict(type='int', required=False, default=22),
            delete=dict(type='bool', required=False, default=False),
            excludes=dict(type='list', elements='str', required=False, default=[]),
            strict_host_key_checking=dict(type='bool', required=False, default=False),
            user_known_hosts_file=dict(type='str', required=False, default="/dev/null"),
            rsync_extra_opts=dict(type='list', elements='str', required=False, default=[]),
        ),
        supports_check_mode=True
    )

    result = run_rsync(module, dry_run=module.check_mode)
    module.exit_json(**result)

if __name__ == '__main__':
    main()
