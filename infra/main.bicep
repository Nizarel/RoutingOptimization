targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the azd environment; drives the resource group name and resource tokens.')
param environmentName string

@minLength(1)
@description('Primary Azure region for all resources.')
param location string = 'eastus2'

@description('Object ID of the principal (user or service principal) to grant Cosmos DB SQL data-plane access. Defaults to the deploying user.')
param principalId string = ''

@allowed(['User', 'ServicePrincipal'])
@description('Type of the principal granted data-plane access.')
param principalType string = 'User'

@allowed(['true', 'false'])
@description('Set to "true" to expose the Container App on a public FQDN. Default "false" (VNet-internal only).')
param externalIngress string = 'false'

var tags = {
  'azd-env-name': environmentName
}

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var rgName = 'rg-${environmentName}'
// ACR names must be 5-50 alphanumeric only; strip hyphens.
var acrName = take('acrrt${replace(resourceToken, '-', '')}', 50)
var externalIngressBool = (externalIngress == 'true')

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: rgName
  location: location
  tags: tags
}

module identity 'modules/identity.bicep' = {
  name: 'identity'
  scope: rg
  params: {
    location: location
    tags: tags
    name: 'id-rt-${resourceToken}'
  }
}

module network 'modules/network.bicep' = {
  name: 'network'
  scope: rg
  params: {
    location: location
    tags: tags
    vnetName: 'vnet-rt-${resourceToken}'
  }
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  scope: rg
  params: {
    location: location
    tags: tags
    workspaceName: 'log-rt-${resourceToken}'
    appInsightsName: 'appi-rt-${resourceToken}'
  }
}

module registry 'modules/registry.bicep' = {
  name: 'registry'
  scope: rg
  params: {
    location: location
    tags: tags
    name: acrName
    pullPrincipalId: identity.outputs.principalId
  }
}

module maps 'modules/maps.bicep' = {
  name: 'maps'
  scope: rg
  params: {
    tags: tags
    name: 'maps-rt-${resourceToken}'
    readerPrincipalId: identity.outputs.principalId
  }
}

module cosmos 'modules/cosmos.bicep' = {
  name: 'cosmos'
  scope: rg
  params: {
    location: location
    tags: tags
    accountName: 'cosmos-rt-${resourceToken}'
    databaseName: 'routing_optimization'
    principalId: principalId
    appPrincipalId: identity.outputs.principalId
  }
}

module kv 'modules/keyvault.bicep' = {
  name: 'keyvault'
  scope: rg
  params: {
    location: location
    tags: tags
    name: 'kv-rt-${resourceToken}'
    principalId: principalId
    principalType: principalType
    appPrincipalId: identity.outputs.principalId
  }
}

module containerapp 'modules/containerapp.bicep' = {
  name: 'containerapp'
  scope: rg
  params: {
    location: location
    tags: tags
    environmentName: 'cae-rt-${resourceToken}'
    appName: 'ca-rt-${resourceToken}'
    logAnalyticsWorkspaceId: monitoring.outputs.workspaceId
    logAnalyticsCustomerId: monitoring.outputs.workspaceCustomerId
    infrastructureSubnetId: network.outputs.acaSubnetId
    userAssignedIdentityId: identity.outputs.id
    userAssignedIdentityClientId: identity.outputs.clientId
    acrLoginServer: registry.outputs.loginServer
    cosmosEndpoint: cosmos.outputs.endpoint
    cosmosDatabase: cosmos.outputs.databaseName
    keyVaultUri: kv.outputs.uri
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    externalIngress: externalIngressBool
    azdServiceName: 'mcp'
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_TENANT_ID string = subscription().tenantId

output AZURE_COSMOS_ENDPOINT string = cosmos.outputs.endpoint
output AZURE_COSMOS_DATABASE string = cosmos.outputs.databaseName
output AZURE_COSMOS_ACCOUNT_NAME string = cosmos.outputs.accountName

output AZURE_KEY_VAULT_NAME string = kv.outputs.name
output AZURE_KEY_VAULT_URI string = kv.outputs.uri

output AZURE_CLIENT_ID string = identity.outputs.clientId
output AZURE_USER_ASSIGNED_IDENTITY_NAME string = identity.outputs.name

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.outputs.loginServer
output AZURE_CONTAINER_REGISTRY_NAME string = registry.outputs.name

output AZURE_CONTAINER_APP_NAME string = containerapp.outputs.appName
output AZURE_CONTAINER_APP_FQDN string = containerapp.outputs.appFqdn
output AZURE_CONTAINER_APPS_ENVIRONMENT_NAME string = containerapp.outputs.environmentName

output APPLICATIONINSIGHTS_CONNECTION_STRING string = monitoring.outputs.appInsightsConnectionString
output AZURE_LOG_ANALYTICS_WORKSPACE_NAME string = monitoring.outputs.workspaceName

output AZURE_MAPS_CLIENT_ID string = identity.outputs.clientId

output AZURE_VNET_NAME string = network.outputs.vnetName
