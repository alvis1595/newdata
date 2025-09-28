# -*- coding: utf-8 -*-
"""
Ansible module: mysql_shell
Ejecuta consultas MySQL/MariaDB con el binario `mysql`, pasando credenciales
mediante --defaults-file (archivo temporal 0600).
"""

from ansible.module_utils.basic import AnsibleModule
import os
import tempfile
import subprocess
import shlex

DOCUMENTATION = r'''
---
module: mysql_shell
short_description: Ejecuta consultas MySQL con el binario mysql usando defaults-file (seguro)
version_added: "1.0.8"
author: "Alibaba"
description:
  - Ejecuta consultas (SELECT/INSERT/UPDATE/DELETE) con el cliente mysql.
  - La contraseña se pasa mediante --defaults-file (archivo temporal 0600).
  - Se escapan/citan los valores para soportar #, comillas y backslashes.
options:
  login_user:
    type: str
    required: true
  login_password:
    type: str
    required: true
    no_log: true
  login_host:
    type: str
    required: false
    default: "localhost"
  login_port:
    type: int
    required: false
    default: 3306
  login_db:
    type: str
    required: false
    default: ""
  query:
    type: str
    required: true
  timeout:
    type: int
    required: false
    default: 300
  mysql_path:
    type: str
    required: false
    default: "mysql"
requirements:
  - mysql (cliente) o mariadb-client instalado en el EE
'''

RETURN = r'''
rc:
  type: int
stdout:
  type: str
stderr:
  type: str
changed:
  type: bool
failed:
  type: bool
cmd:
  type: str
'''

def _escape_opt(val: str) -> str:
    """
    Escapa comillas dobles y backslashes para archivos de opciones de MySQL,
    y convierte saltos de línea. Devuelve el valor entre comillas dobles.
    """
    return '"' + val.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'

def write_defaults_file(user, password, host, port, database):
    """
    Crea un archivo temporal [client] con permisos 0600 para --defaults-file.
    Cita/escapa todos los valores para que # no inicie comentarios.
    """
    fd, path = tempfile.mkstemp(prefix="ansible_mysql_", text=True)
    os.close(fd)
    os.chmod(path, 0o600)
    lines = ["[client]"]
    if user:
        lines.append(f"user={_escape_opt(user)}")
    if password:
        lines.append(f"password={_escape_opt(password)}")
    if host:
        lines.append(f"host={_escape_opt(host)}")
    # port es numérico; sólo escríbelo si viene (permite default(omit) en Ansible)
    if port is not None:
        try:
            lines.append(f"port={int(port)}")
        except Exception:
            pass
    if database:
        lines.append(f"database={_escape_opt(database)}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path

def run_mysql(mysql_path, defaults_file, query, timeout):
    """
    Ejecuta `mysql --defaults-file=... --protocol=TCP -N -e "<query>"` con timeout.
    Devuelve (rc, out, err, cmd_list).
    """
    cmd = [mysql_path, f"--defaults-file={defaults_file}", "--protocol=TCP", "-N", "-e", query]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        out, err = proc.communicate(timeout=timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        rc = 124
        err = (err or "") + "\nTimeoutExpired: consulta excedió el timeout"
    return rc, (out or ""), (err or ""), cmd

def main():
    module = AnsibleModule(
        argument_spec=dict(
            login_user=dict(type='str', required=True),
            login_password=dict(type='str', required=True, no_log=True),
            login_host=dict(type='str', required=False, default='localhost'),
            login_port=dict(type='int', required=False, default=3306),
            login_db=dict(type='str', required=False, default=''),
            query=dict(type='str', required=True),
            timeout=dict(type='int', required=False, default=300),
            mysql_path=dict(type='str', required=False, default='mysql'),
        ),
        supports_check_mode=False
    )

    p = module.params
    defaults_path = None

    try:
        defaults_path = write_defaults_file(
            p['login_user'], p['login_password'], p['login_host'], p.get('login_port'), p['login_db']
        )
        rc, out, err, cmd_list = run_mysql(
            p['mysql_path'], defaults_path, p['query'], p['timeout']
        )
    except Exception as e:
        try:
            if defaults_path and os.path.exists(defaults_path):
                os.remove(defaults_path)
        except Exception:
            pass
        module.fail_json(msg=f"Error ejecutando mysql: {e}")

    # Limpieza del archivo temporal
    try:
        if defaults_path and os.path.exists(defaults_path):
            os.remove(defaults_path)
    except Exception:
        err = (err or "") + "\n[warning] No se pudo borrar defaults-file"

    result = dict(
        rc=rc,
        stdout=out.strip(),
        stderr=err.strip(),
        changed=(rc == 0),
        failed=(rc != 0),
        cmd=" ".join(shlex.quote(x) for x in cmd_list),
    )

    if rc != 0:
        module.fail_json(msg="mysql retornó código distinto de 0", **result)

    module.exit_json(**result)

if __name__ == '__main__':
    main()
