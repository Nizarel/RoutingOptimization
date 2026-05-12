@description('Azure region for the Maps account metadata. Maps is a global service; this affects metadata only.')
param location string = 'global'

@description('Tags applied to the Maps account.')
param tags object = {}

@minLength(1)
@maxLength(98)
@description('Azure Maps account name.')
param name string

@description('Object ID of the principal (typically a UAMI) granted Azure Maps Data Reader. Empty to skip.')
param readerPrincipalId string = ''

resource maps 'Microsoft.Maps/accounts@2023-06-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'G2'
  }
  kind: 'Gen2'
  properties: {
    disableLocalAuth: true
  }
}

// Azure Maps Data Reader
var mapsDataReaderRoleId = '423170ca-a8f6-4b0f-8487-9e4eb8f49bfa'

resource readerRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(readerPrincipalId)) {
  scope: maps
  name: guid(maps.id, readerPrincipalId, mapsDataReaderRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', mapsDataReaderRoleId)
    principalId: readerPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output id string = maps.id
output name string = maps.name
