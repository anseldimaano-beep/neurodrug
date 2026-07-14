{{/*
NeuroDrug Helm Helpers
FIX C7: The original deployment.yaml contained only:
  {{- include "neurodrug.deployment" . -}}
but _helpers.tpl was never created, so `helm install` raised:
  Error: function "neurodrug.deployment" not defined

This file defines all named templates used by the chart.
*/}}

{{/*
Expand the name of the chart.
*/}}
{{- define "neurodrug.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "neurodrug.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "neurodrug.labels" -}}
helm.sh/chart: {{ include "neurodrug.chart" . }}
{{ include "neurodrug.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "neurodrug.selectorLabels" -}}
app.kubernetes.io/name: {{ include "neurodrug.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Chart label
*/}}
{{- define "neurodrug.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
neurodrug.deployment — the main API Deployment manifest.
Referenced by templates/deployment.yaml.
*/}}
{{- define "neurodrug.deployment" -}}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "neurodrug.fullname" . }}-api
  namespace: {{ .Release.Namespace | default "neurodrug" }}
  labels:
    {{- include "neurodrug.labels" . | nindent 4 }}
    app.kubernetes.io/component: api
spec:
  replicas: {{ .Values.replicaCount | default 2 }}
  selector:
    matchLabels:
      {{- include "neurodrug.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: api
  template:
    metadata:
      labels:
        {{- include "neurodrug.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: api
    spec:
      containers:
        - name: api
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
          imagePullPolicy: {{ .Values.image.pullPolicy | default "IfNotPresent" }}
          ports:
            - name: http
              containerPort: 8000
              protocol: TCP
          env:
            - name: POSTGRES_HOST
              valueFrom:
                secretKeyRef:
                  name: {{ include "neurodrug.fullname" . }}-secrets
                  key: POSTGRES_HOST
            - name: POSTGRES_DB
              valueFrom:
                secretKeyRef:
                  name: {{ include "neurodrug.fullname" . }}-secrets
                  key: POSTGRES_DB
            - name: POSTGRES_USER
              valueFrom:
                secretKeyRef:
                  name: {{ include "neurodrug.fullname" . }}-secrets
                  key: POSTGRES_USER
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ include "neurodrug.fullname" . }}-secrets
                  key: POSTGRES_PASSWORD
            - name: SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: {{ include "neurodrug.fullname" . }}-secrets
                  key: SECRET_KEY
            - name: REDIS_URL
              value: "redis://{{ include "neurodrug.fullname" . }}-redis:6379/0"
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 30
            periodSeconds: 15
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            initialDelaySeconds: 10
            periodSeconds: 10
            failureThreshold: 3
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
{{- end }}
