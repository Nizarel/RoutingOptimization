@description('Azure region.')
param location string

@description('Tags applied to all resources.')
param tags object = {}

@description('Existing Container Apps managed environment resource ID.')
param environmentId string

@description('Container App name.')
param appName string

@description('Resource ID of the user-assigned managed identity bound to the Container App.')
param userAssignedIdentityId string

@description('Client ID of the user-assigned managed identity (for AZURE_CLIENT_ID env var).')
param userAssignedIdentityClientId string

@description('ACR login server (e.g. acrrtxxx.azurecr.io). Used for image pull via UAMI.')
param acrLoginServer string

@description('Container image. Defaults to a placeholder; azd swaps this on first deploy.')
param image string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Foundry OpenAI endpoint (https://<sub>.openai.azure.com/).')
param foundryOpenAiEndpoint string

@description('Foundry model deployment name.')
param foundryDeploymentName string

@description('Foundry project endpoint (for tracing/eval).')
param foundryProjectEndpoint string

@description('Application Insights connection string.')
param appInsightsConnectionString string

@description('Internal MCP base URL (e.g. https://ca-rt-xxx.internal.<env-domain>/mcp).')
param mcpBaseUrl string

@description('Key Vault secret URI for the MCP API key.')
param mcpApiKeySecretUri string

@description('Set to true for external (public) ingress.')
param externalIngress bool = false

@description('CPU cores.')
param cpu string = '0.5'

@description('Memory.')
param memory string = '1.0Gi'

@description('Minimum replicas.')
param minReplicas int = 1

@description('Maximum replicas.')
param maxReplicas int = 3

@description('Ingress target port (HTTP).')
param targetPort int = 8080

@description('Service tag matching azure.yaml services.<name>.')
param azdServiceName string = 'agent'

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  tags: union(tags, {
    'azd-service-name': azdServiceName
  })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: externalIngress
        targetPort: targetPort
        transport: 'auto'
        allowInsecure: false
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          server: acrLoginServer
          identity: userAssignedIdentityId
        }
      ]
      secrets: [
        {
          name: 'mcp-api-key'
          keyVaultUrl: mcpApiKeySecretUri
          identity: userAssignedIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'agent'
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            { name: 'AZURE_CLIENT_ID',                       value: userAssignedIdentityClientId }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'AZURE_OPENAI_ENDPOINT',                 value: foundryOpenAiEndpoint }
            { name: 'AZURE_OPENAI_DEPLOYMENT',               value: foundryDeploymentName }
            { name: 'AZURE_OPENAI_API_VERSION',              value: '2024-10-21' }
            { name: 'FOUNDRY_PROJECT_ENDPOINT',              value: foundryProjectEndpoint }
            { name: 'MCP_BASE_URL',                          value: mcpBaseUrl }
            { name: 'MCP_API_KEY',                           secretRef: 'mcp-api-key' }
            { name: 'AGENT_HTTP_HOST',                       value: '0.0.0.0' }
            { name: 'AGENT_HTTP_PORT',                       value: string(targetPort) }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: targetPort
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 30
              timeoutSeconds: 3
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/healthz'
                port: targetPort
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 15
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

output appId string = app.id
output appName string = app.name
output appFqdn string = app.properties.configuration.ingress.fqdn
