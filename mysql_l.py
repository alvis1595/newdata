# -*- coding: utf-8 -*-
"""
Ansible module: mysql_shell
Ejecuta consultas MySQL/MariaDB con el binario `mysql`, pasando credenciales
mediante --defaults-extra-file (evita exponer la contraseña en CLI/logs).

Requisitos en el EE:
  - Cliente mysql/mariadb en PATH (p.ej. paquete `mariadb` en RHEL/UBI).
"""

from ansible.module_utils.basic import AnsibleModule
import os
import tempfile
import subprocess
import shlex

DOCUMENTATION = r'''
---
module: mysql_shell
short_description: Ejecuta consultas MySQL con el binario mysql usando defaults-extra-file (seguro)
version_added: "1.0.0"
author: "alvis1595 (+ ChatGPT)"
description:
  - Ejecuta consultas (SELECT/INSERT/UPDATE/DELETE) con el cliente mysql.
  - La contraseña se pasa mediante --defaults-extra-file (archivo temporal 0600).
options:
  login_user:
    description: Usuario MySQL
    type: str
    required: true
  login_password:
    description: Contraseña MySQL
    type: str
    required: true
    no_log: true
  login_host:
    description: Host MySQL
    type: str
    required: false
    default: "localhost"
  login_port:
    description: Puerto MySQL
    type: int
    required: false
    default: 3306
  login_db:
    description: Base de datos por defecto
    type: str
    required: false
    default: ""
  query:
    description: Consulta SQL a ejecutar (pasada con -e)
    type: str
    required: true
  timeout:
    description: Timeout en segundos para la ejecución
    type: int
    required: false
    default: 300
  mysql_path:
    description: Ruta o nombre del binario mysql
    type: str
    required: false
    default: "mysql"
requirements:
  - mysql (cliente) o mariadb-client instalado en el EE
'''

RETURN = r'''
rc:
  description: Código de salida del cliente mysql
  type: int
stdout:
  description: Salida estándar del comando mysql (sin credenciales)
  type: str
stderr:
  description: Salida de error
  type: str
changed:
  description: true si rc == 0
  type: bool
failed:
  description: true si rc != 0
  type: bool
cmd:
  description: Comando ejecutado (sanitizado, sin credenciales)
  type: str
'''

def write_defaults_file(user, password, host, port, database):
    """
    Crea un archivo temporal [client] con permisos 0600 para --defaults-extra-file.
    """
    fd, path = tempfile.mkstemp(prefix="ansible_mysql_", text=True)
    os.close(fd)
    os.chmod(path, 0o600)
    lines = ["[client]"]
    if user:
        lines.append(f"user={user}")
    if password:
        lines.append(f"password={password}")
    if host:
        lines.append(f"host={host}")
    if port:
        lines.append(f"port={int(port)}")
    if database:
        lines.append(f"database={database}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path

def run_mysql(mysql_path, defaults_file, query, timeout):
    """
    Ejecuta `mysql --defaults-extra-file=... -N -e "<query>"` con timeout.
    Devuelve (rc, out, err). No expone credenciales.
    """
    cmd = [mysql_path, f"--defaults-extra-file={defaults_file}", "-N", "-e", query]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True  # compatible con Py < 3.7; equivale a text=True
        )
        out, err = proc.communicate(timeout=timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        rc = 124  # código típico para timeout
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
        # 1) defaults-extra-file temporal (0600)
        defaults_path = write_defaults_file(
            p['login_user'], p['login_password'], p['login_host'], p['login_port'], p['login_db']
        )

        # 2) Ejecutar cliente mysql con timeout
        rc, out, err, cmd_list = run_mysql(
            p['mysql_path'], defaults_path, p['query'], p['timeout']
        )

    except Exception as e:
        # limpieza antes de fallar
        try:
            if defaults_path and os.path.exists(defaults_path):
                os.remove(defaults_path)
        except Exception:
            pass
        module.fail_json(msg=f"Error ejecutando mysql: {e}")

    # 3) Limpieza del archivo temporal
    try:
        if defaults_path and os.path.exists(defaults_path):
            os.remove(defaults_path)
    except Exception:
        # No fallamos por esto, solo lo agregamos a stderr
        err = (err or "") + "\n[warning] No se pudo borrar defaults-extra-file"

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

