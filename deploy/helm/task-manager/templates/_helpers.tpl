{{- define "task-manager.fullname" -}}
{{- .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}

{{- define "task-manager.selectorLabels" -}}
app.kubernetes.io/name: task-manager
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "task-manager.labels" -}}
{{ include "task-manager.selectorLabels" . }}
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: task-manager
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{/* Image reference. Refuses an empty or "latest" tag. */}}
{{- define "task-manager.image" -}}
{{- $tag := .Values.image.tag | toString -}}
{{- if or (eq $tag "") (eq $tag "latest") -}}
{{- fail "image.tag must be set to an immutable tag (e.g. the git SHA); empty and \"latest\" are not allowed" -}}
{{- end -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end -}}

{{/*
Environment shared by the web pods and the migration Job. Kept inline
(no ConfigMap) because the migration hook runs before the chart's normal
resources are created.
*/}}
{{- define "task-manager.env" -}}
- name: SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secretKey.existingSecret }}
      key: {{ .Values.secretKey.key }}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ .Values.database.secretName }}
      key: {{ .Values.database.secretKey }}
- name: ALLOWED_HOSTS
  value: {{ .Values.host | quote }}
- name: CSRF_TRUSTED_ORIGINS
  value: {{ printf "%s://%s" .Values.scheme .Values.host | quote }}
{{- range $name, $value := .Values.config }}
- name: {{ $name }}
  value: {{ $value | toString | quote }}
{{- end }}
{{- end -}}

{{- define "task-manager.probe" -}}
httpGet:
  path: {{ .probe.path }}
  port: http
  # Django checks the Host header against ALLOWED_HOSTS, and the kubelet
  # would otherwise send the pod IP.
  httpHeaders:
    - name: Host
      value: {{ .host | quote }}
periodSeconds: {{ .probe.periodSeconds }}
{{- with .probe.timeoutSeconds }}
timeoutSeconds: {{ . }}
{{- end }}
failureThreshold: {{ .probe.failureThreshold }}
{{- end -}}
