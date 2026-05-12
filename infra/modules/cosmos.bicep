@description('Azure region for the Cosmos account.')
param location string

@description('Tags applied to all resources.')
param tags object = {}

@description('Cosmos DB account name (3-44 chars, lowercase, alphanumeric + hyphens).')
param accountName string

@description('SQL database name.')
param databaseName string = 'routing_optimization'

@description('Object ID of the principal (typically the deploying user) that gets Cosmos SQL data-plane access. Empty to skip.')
param principalId string = ''

@description('Object ID of the application principal (typically a UAMI) that gets Cosmos SQL data-plane access at runtime. Empty to skip.')
param appPrincipalId string = ''

resource account 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: accountName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    enableAutomaticFailover: false
    enableMultipleWriteLocations: false
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    capabilities: [
      { name: 'EnableServerless' }
    ]
    disableLocalAuth: false  // kept enabled for emulator/tooling fallback; data-plane uses RBAC
    publicNetworkAccess: 'Enabled'
  }
}

resource db 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: account
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
  }
}

// --- Containers (spec §13.2) ---------------------------------------------

var containers = [
  { name: 'locations',          partitionKey: '/location_type', defaultTtl: -1 }
  { name: 'trailer_types',      partitionKey: '/trailer_class', defaultTtl: -1 }
  { name: 'state_restrictions', partitionKey: '/state',         defaultTtl: -1 }
  { name: 'order_boards',       partitionKey: '/order_group',   defaultTtl: 2592000 }   // 30d
  { name: 'route_history',      partitionKey: '/dc_code',       defaultTtl: 7776000 }   // 90d
  { name: 'matrix_cache',       partitionKey: '/profile',       defaultTtl: 86400 }     // 24h
  { name: 'districts',          partitionKey: '/dc_code',       defaultTtl: -1 }
]

resource cosmosContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for c in containers: {
  parent: db
  name: c.name
  properties: {
    resource: {
      id: c.name
      partitionKey: {
        paths: [c.partitionKey]
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [{ path: '/*' }]
        excludedPaths: [{ path: '/"_etag"/?' }]
      }
      defaultTtl: c.defaultTtl
    }
  }
}]

// --- RBAC: assign Cosmos DB Built-in Data Contributor to the deploying principal --

var dataContributorRoleId = '00000000-0000-0000-0000-000000000002'

resource roleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = if (!empty(principalId)) {
  parent: account
  name: guid(account.id, principalId, dataContributorRoleId)
  properties: {
    roleDefinitionId: '${account.id}/sqlRoleDefinitions/${dataContributorRoleId}'
    principalId: principalId
    scope: account.id
  }
}

resource appRoleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = if (!empty(appPrincipalId)) {
  parent: account
  name: guid(account.id, appPrincipalId, dataContributorRoleId)
  properties: {
    roleDefinitionId: '${account.id}/sqlRoleDefinitions/${dataContributorRoleId}'
    principalId: appPrincipalId
    scope: account.id
  }
}

output endpoint string = account.properties.documentEndpoint
output accountName string = account.name
output databaseName string = databaseName
