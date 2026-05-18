@description('Azure region.')
param location string

@description('Tags applied to network resources.')
param tags object = {}

@description('Virtual network name.')
param vnetName string

@description('Address space for the VNet (single CIDR).')
param vnetAddressPrefix string = '10.30.0.0/16'

@description('Subnet name reserved for the Container Apps environment infrastructure.')
param acaSubnetName string = 'snet-aca-infra'

@description('Address prefix for the ACA infrastructure subnet (must be /23 or larger for Consumption profile).')
param acaSubnetPrefix string = '10.30.0.0/23'

@description('Subnet name reserved for private endpoints (Cosmos, Key Vault, etc.).')
param peSubnetName string = 'snet-pe'

@description('Address prefix for the private-endpoint subnet.')
param peSubnetPrefix string = '10.30.2.0/24'

resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [vnetAddressPrefix]
    }
    subnets: [
      {
        name: acaSubnetName
        properties: {
          addressPrefix: acaSubnetPrefix
          delegations: [
            {
              name: 'aca-delegation'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: peSubnetName
        properties: {
          addressPrefix: peSubnetPrefix
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

output vnetId string = vnet.id
output vnetName string = vnet.name
output acaSubnetId string = '${vnet.id}/subnets/${acaSubnetName}'
output peSubnetId string = '${vnet.id}/subnets/${peSubnetName}'
