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

var tags = {
  'azd-env-name': environmentName
}

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var rgName = 'rg-${environmentName}'

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: rgName
  location: location
  tags: tags
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
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_COSMOS_ENDPOINT string = cosmos.outputs.endpoint
output AZURE_COSMOS_DATABASE string = cosmos.outputs.databaseName
output AZURE_COSMOS_ACCOUNT_NAME string = cosmos.outputs.accountName
output AZURE_KEY_VAULT_NAME string = kv.outputs.name
output AZURE_KEY_VAULT_URI string = kv.outputs.uri
