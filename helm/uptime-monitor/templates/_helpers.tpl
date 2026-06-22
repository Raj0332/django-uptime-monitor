{{/*
_helpers.tpl — reusable template snippets. Files starting with "_" are NOT
rendered into Kubernetes objects; they only define named templates you can
{{ include }} elsewhere. This keeps labels consistent across every resource.
*/}}

{{/* Common labels stamped on every object. Helps `kubectl get all -l ...`
     and tells you which release/chart created a resource. */}}
{{- define "uptime-monitor.labels" -}}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}
