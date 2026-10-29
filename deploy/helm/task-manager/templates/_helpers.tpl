{{- define "task-manager.fullname" -}}
{{- .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}

{{- define "task-manager.selectorLabels" -}}
app.kubernetes.io/name: task-manager
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "task-manager.labels" -}}
{{ include "task-manager.selectorLabels" . }}
app.kubernetes.io/version: {{ .Values.image.tag | toString | trunc 63 | trimSuffix "-" | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: task-manager
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{/*
Image reference: repository:tag, or repository:tag@digest when a digest is
set (the digest is what's pulled and verified; the tag is for humans).
Refuses an empty or "latest" tag and a malformed digest.
*/}}
{{- define "task-manager.image" -}}
{{- $tag := .Values.image.tag | toString -}}
{{- if or (eq $tag "") (eq $tag "latest") -}}
{{- fail "image.tag must be set to an immutable tag (e.g. the git SHA); empty and \"latest\" are not allowed" -}}
{{- end -}}
{{- $digest := .Values.image.digest | default "" | toString -}}
{{- if $digest -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" $digest) -}}
{{- fail (printf "image.digest must look like sha256:<64 hex chars>, got %q" $digest) -}}
{{- end -}}
{{- printf "%s:%s@%s" .Values.image.repository $tag $digest -}}
{{- else -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end -}}
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
