#!/usr/bin/env bash

trailer='>>>>>>> '
sshpass_cmd="/usr/bin/sshpass -p $ESXI_PWD"
host="$ESXI_HOST"

echo -e ${trailer} "Adding VNC in ESXi firewall on host $host"
	${sshpass_cmd} scp root@${host}:/etc/vmware/firewall/service.xml ./service.xml."${host}"
	fw_pol=$(grep -E '<id>vnc</id>' ./service.xml."${host}")
	if [ -z "$fw_pol" ]; then
 		sed -i "s/<\/ConfigRoot>//" ./service.xml."${host}"
		echo -e "
  		<service id='0033'>
    		<id>vnc</id>
    		<rule id='0000'>
    	  		<direction>inbound</direction>
      			<protocol>tcp</protocol>
      			<porttype>dst</porttype>
      			<port>
        			<begin>5900</begin>
        			<end>6300</end>
      			</port>
    		</rule>
    		<enabled>true</enabled>
    		<required>false</required>
  		</service>
		</ConfigRoot>" >> ./service.xml.${host}
	 	${sshpass_cmd} scp ./service.xml."${host}" root@"${host}":/etc/vmware/firewall/
	 	${sshpass_cmd} ssh -o StrictHostKeyChecking=no root@"${host}" mv /etc/vmware/firewall/service.xml /etc/vmware/firewall/service.xml.old
 		${sshpass_cmd} ssh -o StrictHostKeyChecking=no root@"${host}" mv /etc/vmware/firewall/service.xml.${host} /etc/vmware/firewall/service.xml
 		${sshpass_cmd} ssh -o StrictHostKeyChecking=no root@"${host}" esxcli network firewall refresh
 		${sshpass_cmd} ssh -o StrictHostKeyChecking=no root@"${host}" 'if [ ! -d /store/firewall ]; then mkdir /store/firewall; fi'
 		${sshpass_cmd} ssh -o StrictHostKeyChecking=no root@"${host}" cp /etc/vmware/firewall/service.xml /store/firewall/service.xml
		${sshpass_cmd} ssh -o StrictHostKeyChecking=no root@"${host}" 'sed -i "s/exit 0//" /etc/rc.local.d/local.sh'
        ${sshpass_cmd} ssh -o StrictHostKeyChecking=no root@"${host}" 'echo -e "
        cp /store/firewall/service.xml /etc/vmware/firewall/service.xml
 	 	esxcli network firewall refresh
 	 	exit 0" >> /etc/rc.local.d/local.sh'
	fi
