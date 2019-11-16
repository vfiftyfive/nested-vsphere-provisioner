from pyVmomi import vim
import nested_vsphere.utils as utils
import re
import random
import time

trailer = ">>>>>>> "


class VESX(object):
    def __init__(self, vm_name, host, datastore, vmfolder, network, mgmt_network, iso, mem, vcpu, si,
                 guestid='vmkernel6Guest', vmx_version='vmx-11', disk_size=8):
        self.vm_name = vm_name
        self.vm_mo = None
        self.si = si
        self.guestid = guestid
        self.vmx_version = vmx_version
        self.disk_size = disk_size

        content = self.si.content
        try:
            self.host = utils.get_obj(content, [vim.HostSystem], host)
        except ValueError:
            raise
        try:
            self.datastore = utils.validate_datastore(content, datastore, self.host)
        except ValueError:
            raise
        try:
            self.network = utils.validate_network(content, network, self.host)
            self.mgmt_network = utils.validate_network(content, mgmt_network, self.host)
        except ValueError:
            raise
        try:
            self.vmfolder = utils.get_obj(si.content, [vim.Folder], vmfolder)
        except ValueError:
            raise
        try:
            iso_split = iso.split('/')
            iso_filename = iso_split.pop()
            j = '/'
            top_lv = iso_split[0].split().pop()
            iso_datastore = re.sub('\[|\]', '', iso_split.pop(0).split()[0])
            iso_folder = j.join([top_lv] + iso_split)
        except IndexError, e:
            print e
            iso_split = iso.split()
            iso_filename = iso_split.pop()
            iso_datastore = re.sub('\[|\]', '', iso_split[0])
            iso_folder = ''

        print trailer + "Validating Datastore for VM " + self.vm_name
        res = utils.validate_datastore_file(utils.get_obj(self.si.content, [vim.Datastore], iso_datastore), iso_folder,
                                            iso_filename)
        if res.info.state == 'error':
            raise ValueError(res.info.error.msg)
        else:
            self.iso = iso

        self.mem = mem
        self.vcpu = vcpu
        datastore_path = '[' + self.datastore.name + '] ' + self.vm_name
        add = vim.vm.device.VirtualDeviceSpec.Operation.add
        create = vim.vm.device.VirtualDeviceSpec.FileOperation.create

        if 'dvportgroup' in str(self.network):
            net_spec = utils.create_vds_net_spec(self.network)
            print trailer + "VDS Portgroup found for VM Network"
        else:
            net_spec = utils.create_vss_net_spec(self.network)
            print trailer + "VSS Portgroup found for VM Network"

        if 'dvportgroup' in str(self.mgmt_network):
            net_mgmt_spec = utils.create_vds_net_spec(self.mgmt_network)
            print trailer + "VDS Portgroup found for Management Network"
        else:
            net_mgmt_spec = utils.create_vss_net_spec(self.mgmt_network)
            print trailer + "VSS Portgroup found for Management Network"

        print trailer + "Creating disk controller"
        noSharing = vim.vm.device.VirtualSCSIController.Sharing.noSharing
        disk_ctrl = vim.vm.device.VirtualLsiLogicSASController(busNumber=0, sharedBus=noSharing)
        ctrl_spec = vim.vm.device.VirtualDeviceSpec(device=disk_ctrl, operation=add)
        con_info = vim.vm.device.VirtualDevice.ConnectInfo(startConnected=True, allowGuestControl=True)
        cdrom_backing_info = vim.vm.device.VirtualCdrom.IsoBackingInfo(fileName=self.iso)
        cdrom = vim.vm.device.VirtualCdrom(backing=cdrom_backing_info, connectable=con_info, controllerKey=201)
        cdrom_spec = vim.vm.device.VirtualDeviceSpec(device=cdrom, operation=add)

        print trailer + "Adding Hard Drive"
        vdisk_backing_info = vim.vm.device.VirtualDisk.FlatVer2BackingInfo(thinProvisioned=True, diskMode='persistent',
                                                                           fileName=datastore_path + r'/' + vm_name +
                                                                                    '.vmdk')
        vdisk = vim.vm.device.VirtualDisk(unitNumber=0, capacityInKB=self.disk_size*1024*1024,
                                          controllerKey=disk_ctrl.key,
                                          backing=vdisk_backing_info)
        vdisk_spec = vim.vm.device.VirtualDeviceSpec(device=vdisk, operation=add, fileOperation=create)

        vnc_rand_port = random.randint(5900, 6300)
        self.vnc_port = vnc_rand_port
        print trailer + "Enabling VNC on port " + str(vnc_rand_port)
        vnc_enabled = vim.option.OptionValue(key='RemoteDisplay.vnc.enabled', value='true')
        vnc_port = vim.option.OptionValue(key='RemoteDisplay.vnc.port', value=str(vnc_rand_port))

        vmx_file = vim.vm.FileInfo(vmPathName='[' + datastore + '] ' + vm_name + '/' + vm_name + '.vmx')
        self.config = vim.vm.ConfigSpec(name=self.vm_name, memoryMB=self.mem, numCPUs=self.vcpu, files=vmx_file,
                                        guestId=self.guestid, version=self.vmx_version, nestedHVEnabled=True,
                                        extraConfig=[vnc_enabled, vnc_port],
                                        deviceChange=[net_mgmt_spec, net_spec, net_spec, net_spec, ctrl_spec,
                                                      cdrom_spec, vdisk_spec])

    def deploy_vm_task(self):
        if 'Cluster' in str(self.host.parent):
            print trailer + "Parent is cluster. Creating Virtual Machine on host {}".format(self.host.name)
            task = self.vmfolder.CreateVM_Task(config=self.config, pool=self.host.parent.resourcePool, host=self.host)
            while task.info.state != 'error' and task.info.state != 'success':
                pass
            return task
        else:
            print trailer + "Parent is host. Creating Virtual Machine on host {}".format(self.host.name)
            task = self.vmfolder.CreateVM_Task(config=self.config, pool=self.host.resourcePool)
            while task.info.state != 'error' and task.info.state != 'success':
                pass
            return task

    def boot(self):
        self.vm_mo = utils.get_obj(self.si.content, [vim.VirtualMachine], self.vm_name)
        task = self.vm_mo.PowerOnVM_Task()
        time.sleep(10)
        self.host = self.vm_mo.runtime.host
        print trailer + "Booting Virtual Machine on host {}".format(self.host.name)
        while task.info.state != 'error' and task.info.state != 'success':
            pass
        return task

    def delete(self):
        pass
