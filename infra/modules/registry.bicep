@description('Azure region.')
param location string

@description('Tags applied to the registry.')
param tags object = {}

@minLength(5)
@maxLength(50)
@description('Container Registry name (alphanumeric, globally unique).')
param name string

@description('Object ID of the principal (typically a UAMI) granted AcrPull. Empty to skip.')
param pullPrincipalId string = ''

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
    anonymousPullEnabled: false
  }
}

// AcrPull
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource pullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(pullPrincipalId)) {
  scope: acr
  name: guid(acr.id, pullPrincipalId, acrPullRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: pullPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output id string = acr.id
output name string = acr.name
output loginServer string = acr.properties.loginServer
