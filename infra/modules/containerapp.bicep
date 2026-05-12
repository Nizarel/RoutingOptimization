@description('Azure region.')
param location string

@description('Tags applied to all resources.')
param tags object = {}

@description('Container Apps managed environment name.')
param environmentName string

@description('Container App name.')
param appName string

@description('Resource ID of the Log Analytics workspace.')
param logAnalyticsWorkspaceId string

@description('Customer ID (workspace ID, not resource ID) of the Log Analytics workspace.')
param logAnalyticsCustomerId string

@description('Resource ID of the subnet delegated to Microsoft.App/environments.')
param infrastructureSubnetId string

@description('Resource ID of the user-assigned managed identity bound to the Container App.')
param userAssignedIdentityId string

@description('Client ID of the user-assigned managed identity (for AZURE_CLIENT_ID env var).')
param userAssignedIdentityClientId string

@description('ACR login server (e.g. acrrtxxx.azurecr.io). Used for image pull via UAMI.')
param acrLoginServer string

@description('Container image. Defaults to a placeholder; azd swaps this on first deploy.')
param image string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Cosmos DB account endpoint URL.')
param cosmosEndpoint string

@description('Cosmos SQL database name.')
param cosmosDatabase string

@description('Key Vault URI (https://<name>.vault.azure.net/).')
param keyVaultUri string

@description('Application Insights connection string.')
param appInsightsConnectionString string

@description('CPU cores (e.g. 0.5).')
param cpu string = '0.5'

@description('Memory (e.g. 1.0Gi).')
param memory string = '1.0Gi'

@description('Minimum replicas.')
param minReplicas int = 1

@description('Maximum replicas.')
param maxReplicas int = 3

@description('Ingress target port (HTTP).')
param targetPort int = 8000

@description('Set to true for external (public) ingress; false for VNet-internal only.')
param externalIngress bool = false

@description('Service tag matching the azure.yaml services.<name> key. Used by azd to discover the app.')
param azdServiceName string = 'mcp'

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: last(split(logAnalyticsWorkspaceId, '/'))
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: infrastructureSubnetId
      internal: externalIngress ? false : true
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    zoneRedundant: false
  }
}

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
    environmentId: environment.id
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
    }
    template: {
      containers: [
        {
          name: 'mcp'
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            { name: 'AZURE_CLIENT_ID',                       value: userAssignedIdentityClientId }
            { name: 'AZURE_COSMOS_ENDPOINT',                 value: cosmosEndpoint }
            { name: 'AZURE_COSMOS_DATABASE',                 value: cosmosDatabase }
            { name: 'AZURE_KEY_VAULT_URI',                   value: keyVaultUri }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'AZURE_MAPS_CLIENT_ID',                  value: userAssignedIdentityClientId }
            { name: 'MCP_TRANSPORT',                         value: 'http' }
            { name: 'MCP_HTTP_HOST',                         value: '0.0.0.0' }
            { name: 'MCP_HTTP_PORT',                         value: string(targetPort) }
          ]
          probes: [
            {
              type: 'Liveness'
              tcpSocket: {
                port: targetPort
              }
              initialDelaySeconds: 10
              periodSeconds: 30
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

output environmentId string = environment.id
output environmentName string = environment.name
output appId string = app.id
output appName string = app.name
output appFqdn string = app.properties.configuration.ingress.fqdn
