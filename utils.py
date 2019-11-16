from pyVim.connect import SmartConnect, Disconnect
from pyVim.task import WaitForTask
from pyVmomi import vim, vmodl
import ssl
import requests
import atexit

def svc_login(host, user, port, password):
    requests.packages.urllib3.disable_warnings()
    context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    context.verify_mode = ssl.CERT_NONE
    si = SmartConnect(host=host, user=user, pwd=password, port=port, sslContext=context)
    atexit.register(Disconnect, si)
    return si

def get_obj(content, vimtype, name):
    obj = None
    container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
    view = container.view
    container.Destroy()
    for v in view:
        if v.name == name:
            obj = v
            break
    if obj is None:
        raise ValueError("Object with name '{}' not found".format(name))
    else:
        return obj

def validate_datastore(content, datastore, host):
    ds_list = host.datastore
    ds_mo = None
    for ds in ds_list:
        if ds.name == datastore:
            ds_mo = get_obj(content, [vim.Datastore], datastore)
    if not ds_mo:
        raise ValueError("Object with name '{}'not found".format(datastore))
    else:
        return ds_mo

def validate_network(content, network, host):
    network_list = host.network
    net_mo = None
    for net in network_list:
        if net.name == network:
            net_mo = get_obj(content, [vim.Network], network)
    if not net_mo:
        raise ValueError("Object with name '{}'not found".format(network))
    else:
        return net_mo

def validate_datastore_file(ds_mo, folder, filename):
    search_spec = vim.host.DatastoreBrowser.SearchSpec()
    search_spec.searchCaseInsensitive = True
    search_spec.matchPattern = filename
    # search_spec.query = [vim.host.DatastoreBrowser.IsoImageQuery()]
    task = ds_mo.browser.SearchDatastoreSubFolders_Task("[{}] {}".format(ds_mo.name, folder), search_spec)
    while task.info.state != 'error' and task.info.state != 'success':
        pass
    return task

def create_vds_net_spec(network_mo):
    dvsUuid = network_mo.config.distributedVirtualSwitch.uuid
    portgroup = vim.dvs.PortConnection(switchUuid=dvsUuid, portgroupKey=network_mo.key)
    backing_info = vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo(port=portgroup)
    e1000 = vim.vm.device.VirtualE1000(backing=backing_info, key=-1)
    net_spec = vim.vm.device.VirtualDeviceSpec(device=e1000,
                                               operation=vim.vm.device.VirtualDeviceSpec.Operation('add'))
    return net_spec

def create_vss_net_spec(network_mo):
    backing_info = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
    backing_info.network = network_mo
    backing_info.deviceName = network_mo.name
    e1000 = vim.vm.device.VirtualE1000(backing=backing_info, key=-1)
    net_spec = vim.vm.device.VirtualDeviceSpec(device=e1000,
                                               operation=vim.vm.device.VirtualDeviceSpec.Operation('add'))
    return net_spec
    
# def wait_for_task(content, task):
#     pc = content.propertyCollector
#     property_filter_spec = vmodl.query.PropertyCollector.FilterSpec()
#     object_spec = vmodl.query.PropertyCollector.ObjectSpec(obj=task)
#     property_filter_spec.objectSet = [object_spec]
#     property_spec = vmodl.query.PropertyCollector.PropertySpec(type=vim.Task, pathSet=[], all=True)
#     property_filter_spec.propSet = [property_spec]
#     pc.CreateFilter(property_filter_spec, True)
#
#     try:
#         version, state = None, None
#
#         while state != vim.TaskInfo.State.success and state != vim.TaskInfo.State.error:
#             update = pc.WaitForUpdates(version)
#             for filter_set in update.filterSet:
#                 for object_set in filter_set.objectSet:
#                     for change in object_set.changeSet:
#                         if change.name == 'info':
#                             state = change.val.state
#                         elif change.name == 'info.state':
#                             state = change.val
#             version = update.version
#
#         if state == vim.TaskInfo.State.success:
#             return state
#         elif state == vim.TaskInfo.State.error:
#             raise task.info.error
#
#     except:
#         raise

def create_VSS(content, host_name, vss_name, vmnic_name, mtu=1500):
    host_system_mo = get_obj(content, [vim.HostSystem], host_name)
    host_network_system_mo = host_system_mo.configManager.networkSystem
    host_virtual_switch_spec = vim.host.VirtualSwitch.Specification()
    host_virtual_switch_spec.mtu = mtu
    found = False
    for p in host_network_system_mo.networkInfo.pnic:
        if p.device == vmnic_name:
            found = True
            break
    if not found:
        return "vmnic {} not found".format(vmnic_name)
    host_virtual_switch_spec.bridge = vim.host.VirtualSwitch.BondBridge(nicDevice=vmnic_name)
    host_virtual_switch_spec.numPorts=64
    host_network_system_mo.AddVirtualSwitch(vswitchName=vss_name, spec=host_virtual_switch_spec)

def create_DVS(content, datacenter_name, vds_name, folder_name=None):
    if folder_name is not None:
        folder_mo = get_obj(content, [vim.Folder], folder_name)
        for c in content.rootFolder.childEntity:
            network_folder_mo_list = [n for n in c.networkFolder.childEntity if n == folder_mo]
            if len(network_folder_mo_list) > 0:
                network_folder_mo = network_folder_mo_list[0]
                break
    else:
        datacenter_mo = get_obj(content, [vim.Datacenter], datacenter_name)
        network_folder_mo = datacenter_mo.networkFolder

    DVS_create_spec = vim.DistributedVirtualSwitch.CreateSpec()
    DVS_create_spec.configSpec = vim.DistributedVirtualSwitch.ConfigSpec()
    DVS_create_spec.configSpec.name = vds_name
    DVS_create_spec.configSpec.uplinkPortPolicy = vim.DistributedVirtualSwitch.NameArrayUplinkPortPolicy()
    DVS_create_spec.configSpec.uplinkPortPolicy.uplinkPortName = ['dvuplink1']

    try:
        DVS_mo_task = network_folder_mo.CreateDVS_Task(spec=DVS_create_spec)
        WaitForTask(DVS_mo_task)
        search_index = content.searchIndex
        return search_index.FindChild(network_folder_mo, vds_name)

    except:
        raise

def add_portgroup_to_VSS(content, host_name, pg_name, vlan_id, vswitch_name):
    host_system_mo = get_obj(content, [vim.HostSystem], host_name)
    host_network_system_mo = host_system_mo.configManager.networkSystem
    vswitch_list = host_network_system_mo.networkConfig.vswitch
    found = False
    for v in vswitch_list:
        if v.name == vswitch_name:
            found = True
            break
    if not found:
        return "vSwitch {} not found".format(vswitch_name)
    host_pg_spec = vim.host.PortGroup.Specification()
    host_pg_spec.name = pg_name
    host_pg_spec.vlanId = vlan_id
    host_pg_spec.vswitchName = vswitch_name
    host_pg_spec.policy = vim.host.NetworkPolicy()
    host_network_system_mo.AddPortGroup(portgrp=host_pg_spec)

def add_portgroup_to_VDS(content, dvs_mo, portgroup_name, vlan_id):
    # This is adding an ephemeral type Portgroup
    vlan_id_spec = vim.dvs.VmwareDistributedVirtualSwitch.VlanIdSpec(vlanId=vlan_id)
    vmware_dvs_port_setting = vim.dvs.VmwareDistributedVirtualSwitch.VmwarePortConfigPolicy()
    vmware_dvs_port_setting.vlan = vlan_id_spec
    dv_portgroup_config_spec = vim.dvs.DistributedVirtualPortgroup.ConfigSpec()
    dv_portgroup_config_spec.name = portgroup_name
    dv_portgroup_config_spec.type = vim.dvs.DistributedVirtualPortgroup.PortgroupType.ephemeral
    dv_portgroup_config_spec.defaultPortConfig = vmware_dvs_port_setting
    try:
        add_portgroup_task = dvs_mo.AddDVPortgroup_Task(spec=[dv_portgroup_config_spec])
        WaitForTask(add_portgroup_task)
        portgroup_name_list = [pg for pg in dvs_mo.portgroup if pg.config.name == portgroup_name]
        return portgroup_name_list[0]

    except:
        raise

def add_trunk_portgroup_to_vds(content, dvs_mo, portgroup_name):
    trunk_vlan_spec = vim.dvs.VmwareDistributedVirtualSwitch.TrunkVlanSpec()
    trunk_vlan_spec.vlanId = [vim.NumericRange(start=1, end=4094)]
    vmware_dvs_port_setting = vim.dvs.VmwareDistributedVirtualSwitch.VmwarePortConfigPolicy()
    vmware_dvs_port_setting.vlan = trunk_vlan_spec
    dv_portgroup_config_spec = vim.dvs.DistributedVirtualPortgroup.ConfigSpec()
    dv_portgroup_config_spec.name = portgroup_name
    dv_portgroup_config_spec.type = vim.dvs.DistributedVirtualPortgroup.PortgroupType.ephemeral
    dv_portgroup_config_spec.defaultPortConfig = vmware_dvs_port_setting
    try:
        add_portgroup_task = dvs_mo.AddDVPortgroup_Task(spec=[dv_portgroup_config_spec])
        WaitForTask(add_portgroup_task)
        portgroup_name_list = [pg for pg in dvs_mo.portgroup if pg.config.name == portgroup_name]
        return portgroup_name_list[0]
    except:
        raise

def delete_VDS_portgroup(content, dvs_name, portgroup_name):
    dvs_container = content.viewManager.CreateContainerView(content.rootFolder, [vim.DistributedVirtualSwitch], recursive=True)
    found = False
    for dvs in dvs_container.view:
        if dvs.name == dvs_name:
            found = True
            break
    if not found:
        return "VDS Object not found - cannot delete"
    found = False
    for pg in dvs.portgroup:
        if pg.name == portgroup_name:
            found = True
            break
    if not found:
        return "Portgroup Object not found - cannot delete"
    try:
        destroy_task = pg.Destroy_Task()
        return WaitForTask(destroy_task)
    except:
        raise

def add_host_to_VDS(content, host_mo, dvs_mo, vmnic):
    pnic_spec = vim.dvs.HostMember.PnicSpec()
    pnic_spec.pnicDevice = vmnic
    host_member_config_spec = vim.dvs.HostMember.ConfigSpec()
    host_member_config_spec.backing = vim.dvs.HostMember.PnicBacking()
    host_member_config_spec.backing.pnicSpec = [pnic_spec]
    host_member_config_spec.host = host_mo
    host_member_config_spec.operation = vim.ConfigSpecOperation.add
    dvs_config_spec = vim.DistributedVirtualSwitch.ConfigSpec()
    dvs_config_spec.host = [host_member_config_spec]
    dvs_config_spec.configVersion = dvs_mo.config.configVersion

    try:
        reconfigure_dvs_task = dvs_mo.ReconfigureDvs_Task(spec=dvs_config_spec)
        return WaitForTask(reconfigure_dvs_task)

    except:
        raise

def evacuate_VDS(content, dvs_mo):
    dvs_config_spec = vim.DistributedVirtualSwitch.ConfigSpec()
    dvs_config_spec.configVersion = dvs_mo.config.configVersion
    list_of_dvs_host_config_spec = []
    for host_member in dvs_mo.config.host:
        dvs_host_config_spec = vim.dvs.HostMember.ConfigSpec()
        dvs_host_config_spec.host = host_member.config.host
        dvs_host_config_spec.operation = vim.ConfigSpecOperation.remove
        list_of_dvs_host_config_spec.append(dvs_host_config_spec)
    dvs_config_spec.host = list_of_dvs_host_config_spec
    try:
        reconfigure_dvs_task = dvs_mo.ReconfigureDvs_Task(dvs_config_spec)
        return WaitForTask(reconfigure_dvs_task)
    except:
        raise

def change_vm_cpu_reservation(content, vm_mo, res_mhz):
    vm_config_spec = vim.vm.ConfigSpec()
    cpu_allocation = vim.ResourceAllocationInfo()
    cpu_allocation.reservation = res_mhz
    vm_config_spec.cpuAllocation = cpu_allocation
    try:
        reconfigure_vm_task = vm_mo.ReconfigVM_Task(vm_config_spec)
        return WaitForTask(reconfigure_vm_task)
    except:
        raise

def change_vm_mem_reservation(content, vm_mo, res_mb):
    vm_config_spec = vim.vm.ConfigSpec()
    mem_reservation = vim.ResourceAllocationInfo()
    mem_reservation.reservation = res_mb
    vm_config_spec.memoryAllocation = mem_reservation
    try: 
        reconfigure_vm_task = vm_mo.ReconfigVM_Task(vm_config_spec)
        return WaitForTask(reconfigure_vm_task)
    except:
        raise

