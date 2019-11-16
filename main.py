#!/usr/bin/env python

import nested_vsphere.utils as utils
import nested_vsphere.vesx as vesx
import sys
import os
import time

def distribute_resources(consumer, resource):
    j = 0
    res = [[] for _ in range(resource)]

    while j < len(consumer):
        for i in range(resource):
            if j == len(consumer):
                break
            res[i].append(consumer[j])
            j += 1
    return res


def main():
    si = utils.svc_login(host=os.environ['HOST'], user=os.environ['USER'], port='443', password=os.environ['PASSWORD'])

    name_list = os.environ['VMNAME_LIST'].split(' ')
    for n in name_list:
        if (not n):
            name_list.remove(n) 

    compute_host_list = os.environ['COMPUTE_HOSTS'].split(' ')
    ks_server=os.environ['KS_SERVER']
    vm_distribution = distribute_resources(name_list, len(compute_host_list))
    host_index = 0
    for host in vm_distribution:
        dest_host = compute_host_list[host_index]
        host_index += 1
        for vm in host:
            try:
                nested_vm = vesx.VESX(vm_name=vm, host=dest_host,
                                      datastore=os.environ['DATASTORE'], vmfolder=os.environ['VMFOLDER'],
                                      network=os.environ['NETWORK'], mgmt_network=os.environ['MGMT_NETWORK'],
                                      iso=os.environ['ISO'], mem=int(os.environ['MEM']), vcpu=int(os.environ['VCPU']),
                                      si=si, guestid=os.environ['GUESTID'], vmx_version=os.environ['VMX_VERSION'],
                                      disk_size=int(os.environ['DISK_SIZE']))
                print "\n\n{}Deploying VM {} on host {}".format(trailer, nested_vm.vm_name, nested_vm.host.name)
                res = nested_vm.deploy_vm_task()
                if res.info.state == 'error':
                    raise ValueError(res.info.error.msg)
                res = nested_vm.boot()
                if res.info.state == 'error':
                    raise ValueError(res.info.error.msg)

                print "{}Connecting VNC console: {}::{}\n".format(trailer, nested_vm.host.name, nested_vm.vnc_port)
                for i in range(8):
                    os.system("vncdo -s {}::{} key tab pause 1".format(nested_vm.host.name, nested_vm.vnc_port))
                os.system("vncdo -s {}::{} type \" ks=http\" keydown shift key : "
                          "keyup shift type //{}/esxi-kickstart.cfg pause 1 key enter"
                          .format(nested_vm.host.name, nested_vm.vnc_port, ks_server))

            except Exception, e:
                print "\nException caught:{}".format(e)

if __name__ == '__main__':
    sys.exit(main())
