{{- define "task-manager-db.name" -}}
{{- default .Release.Name .Values.nameOverride | trunc 50 | trimSuffix "-" -}}
{{- end -}}

{{- define "task-manager-db.labels" -}}
app.kubernetes.io/name: task-manager-db
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: task-manager
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}
