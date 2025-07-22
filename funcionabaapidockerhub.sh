  - name: Obtener etiquetas de Grafana desde Docker Hub
    uri:
      url: "https://registry.hub.docker.com/v2/repositories/grafana/grafana/tags?page_size=100"
      return_content: true
    register: dockerhub_response
  - name: Mostrar etiquetas devueltas (sin filtrar)
    debug:
      msg: "{{ dockerhub_response.json.results | map(attribute='name') | list }}"
  - name: Filtrar etiquetas que parecen versiones válidas
    set_fact:
      grafana_version_tags: >-
        {{
          dockerhub_response.json.results
          | map(attribute='name')
          | select('search', '^\\d+\\.\\d+')
          | reject('search', 'latest')
          | reject('search', 'ubuntu')
          | reject('search', 'main')
          | list
          | sort(reverse=true)
        }}
  - name: Mostrar etiquetas filtradas ordenadas
    debug:
      var: grafana_version_tags
  - name: Establecer la última versión oficial encontrada
    set_fact:
      grafana_latest_version: "{{ grafana_version_tags[0] if grafana_version_tags else 'desconocido' }}"
