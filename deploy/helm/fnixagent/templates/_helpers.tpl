{{/*
FnixAgent Helm Chart 模板辅助函数
*/}}

{{- define "fnixagent.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "fnixagent.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "fnixagent.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
公共标签(所有资源继承)
*/}}
{{- define "fnixagent.labels" -}}
helm.sh/chart: {{ include "fnixagent.chart" . }}
{{ include "fnixagent.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
选择器标签(必须与 Deployment.selector.matchLabels 一致)
*/}}
{{- define "fnixagent.selectorLabels" -}}
app.kubernetes.io/name: {{ include "fnixagent.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Service Account 名称
*/}}
{{- define "fnixagent.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "fnixagent.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Secret 名称
*/}}
{{- define "fnixagent.secretName" -}}
{{- default (printf "%s-secrets" (include "fnixagent.fullname" .)) .Values.secret.name -}}
{{- end -}}

{{/*
数据库连接 URL
- 若 DATABASE_URL 显式设置,直接使用
- 若启用 postgres 子 Chart,自动拼接
- 若启用外部数据库,拼接外部地址
*/}}
{{- define "fnixagent.databaseUrl" -}}
{{- if .Values.env.DATABASE_URL -}}
{{- .Values.env.DATABASE_URL -}}
{{- else if .Values.postgres.enabled -}}
{{- printf "postgresql://fnixagent:%s@%s-postgresql:5432/%s" "$(POSTGRES_PASSWORD)" (include "fnixagent.fullname" .) .Values.postgres.auth.database -}}
{{- else if .Values.externalDatabase.enabled -}}
{{- printf "postgresql://%s:%s@%s:%d/%s" .Values.externalDatabase.user "$(POSTGRES_PASSWORD)" .Values.externalDatabase.host (int .Values.externalDatabase.port) .Values.externalDatabase.database -}}
{{- else -}}
{{- "" -}}
{{- end -}}
{{- end -}}

{{/*
Redis 主机地址
- 若 REDIS_HOST 显式设置,直接使用
- 若启用 redis 子 Chart,使用子 Chart 服务名
- 若启用外部 Redis,使用外部地址
*/}}
{{- define "fnixagent.redisHost" -}}
{{- if .Values.env.REDIS_HOST -}}
{{- .Values.env.REDIS_HOST -}}
{{- else if .Values.redis.enabled -}}
{{- printf "%s-redis-master" (include "fnixagent.fullname" .) -}}
{{- else if .Values.externalRedis.enabled -}}
{{- .Values.externalRedis.host -}}
{{- else -}}
{{- "" -}}
{{- end -}}
{{- end -}}
