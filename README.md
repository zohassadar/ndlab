Python network lab.  Based off of https://github.com/vrnetlab/vrnetlab

Tested in linux to meet my lab needs.  Spawns background instances of qemu for each virtual machine.  Uses python to switch traffic between the machines, with optional switching to a physical nic or to pcap output that can be piped to wireshark.


Known working images:

### Mikrotik
```
chr-6.48.6.vmdk sha256:0160ae167fd69321efcb1b2a10644c972afcfec8275dac4efa45c972d73f6f11
chr-7.6.vmdk sha256:fd0c1dfc7b1e8920afcb40c2852314469f118f7bd412d0b1fecf34293108442e
```

### Arista
```
vEOS-lab-4.29.1F.vmdk sha256:c71e7f545a29c9f7493673cbf2ba5e660b0c8028d47d66abbee3553ef7cf8fef
vEOS-lab-4.28.5M.vmdk sha256:34dc249e1f52014a7b0ddace69bd45d1bdaf9a0e6f91f9f35e40ec2b07ef8e43
Aboot-veos-serial-8.0.1.iso sha256:a1d2c3a751619feb3e3367a7e0c660ebc34b8c72e51b6a05498169d70d7953f4
```

### Cisco XRv9k
```
xrv9k-fullk9-x-7.5.2.qcow2 sha256:06ba7eec38195545399627e4cba3b3b323d460b7587dd1b58017866abd921418
xrv9k-fullk9-x-7.4.2.qcow2 sha256:de6694e125b1180cd66c73be7605120ee638233397c6714c9c2afe7404e2f9af
```

### Cisco IOS Images (From VIRL)
```
viosl2-adventerpriseK9-M_152_May_2018.qcow2 sha256:07bfe23c5d546beba90de352e34c1f8048d73c7b9317993922ba7738936d5854
vios-adventerprisek9-m.SPA.154-3M8.qcow2 sha256:f17b6c74a712f003ea52acca85d1440cf207cdcd7ae2fe946136234ca87f4181
```

### Cisco CSR1000v
```
csr1000v-universalk9.17.03.05-serial.qcow2 sha256:4b8fcc2138845fe74dc7a095c666701806b92c2af57f253e5da986d510ddbc0f
csr1000v-universalk9.17.03.06-serial.qcow2 sha256:a8d3b9cbd0cc7aae432b36e453d213a0fc9c436dca327074a0caa2aebb5cd83b
```


###

`ndlab image discover`


To get started:

Install qemu

Install locally (in a virtual environment preferably):

`pip install -e .`

Put images in $HOME/.ndlab/images

```
$ ndlab image list | grep -v stable
tag                  image
-------------------  --------------------------------------------------------------------------
chr_6.48.6           /home/user/.ndlab/images/chr-6.48.6.vmdk
chr_7.6              /home/user/.ndlab/images/chr-7.6.vmdk
csr_17.03.05         /home/user/.ndlab/images/csr1000v-universalk9.17.03.05-serial.qcow2
csr_17.03.06         /home/user/.ndlab/images/csr1000v-universalk9.17.03.06-serial.qcow2
iosv_154-3M8         /home/user/.ndlab/images/vios-adventerprisek9-m.SPA.154-3M8.qcow2
iosvl2_152           /home/user/.ndlab/images/viosl2-adventerpriseK9-M_152_May_2018.qcow2
veos_4.28.5M         /home/user/.ndlab/images/vEOS-lab-4.28.5M.vmdk
veos_4.29.1F         /home/user/.ndlab/images/vEOS-lab-4.29.1F.vmdk
xrv9k_7.4.2          /home/user/.ndlab/images/xrv9k-fullk9-x-7.4.2.qcow2
xrv9k_7.5.2          /home/user/.ndlab/images/xrv9k-fullk9-x-7.5.2.qcow2
```


Create build images for xrv9k and veos machines.  xrv9k because the first time they boot it takes an incredibly long time.  Subsequent bootups aren't so bad.  The Arista devices will boot into ztp mode initially and require a reboot in order to proceed in non-ztp.


```
ndlab build load  veos_4.28.5M --build-tag stable
ndlab build load  veos_4.29.1F --build-tag stable
ndlab build load  xrv9k_7.4.2 --build-tag stable
ndlab build load  xrv9k_7.5.2 --build-tag stable

ndlab device list

ndlab device start --all

ndlab build configure iosv_154-3M8_stable
ndlab build configure iosvl2_152_stable
ndlab build configure veos_4.28.5M_stable
ndlab build configure veos_4.29.1F_stable
ndlab build configure xrv9k_7.4.2_stable
ndlab build configure xrv9k_7.5.2_stable

$ ndlab image list | grep stable
iosv_154-3M8_stable  /home/user/.ndlab/builds/stable/vios-adventerprisek9-m.SPA.154-3M8.qcow2
iosvl2_152_stable    /home/user/.ndlab/builds/stable/viosl2-adventerpriseK9-M_152_May_2018.qcow2
veos_4.28.5M_stable  /home/user/.ndlab/builds/stable/vEOS-lab-4.28.5M.vmdk
veos_4.29.1F_stable  /home/user/.ndlab/builds/stable/vEOS-lab-4.29.1F.vmdk
xrv9k_7.4.2_stable   /home/user/.ndlab/builds/stable/xrv9k-fullk9-x-7.4.2.qcow2
xrv9k_7.5.2_stable   /home/user/.ndlab/builds/stable/xrv9k-fullk9-x-7.5.2.qcow2


ndlab device add --tag veos_4.29.1F_stable --name A1
ndlab device add --tag iosvl2_152_stable --name C2


$ ndlab device list
name    console_port    qemu_port    state
------  --------------  -----------  -------
A1                                   stopped
C2                                   stopped


ndlab device start A1 C2


$ ndlab device list
name      console_port    qemu_port  state
------  --------------  -----------  -------
A1               57369        35805  running
C2               39715        57721  running

ndlab bridge add --tcp-endpoint A1/0 --tcp-endpoint C2/0 --name AtoC

$ ndlab bridge list
bridge    state    device      index    port
--------  -------  --------  -------  ------
AtoC      stopped  A1              0   49953
AtoC      stopped  C2              0   59217


ndlab bridge start AtoC



$ ndlab console A1
Trying 127.0.0.1...
Connected to localhost.
Escape character is '^]'.


veos login: admin123
Password:
veos>show lldp neigh
Last table change time   : 0:00:09 ago
Number of table inserts  : 1
Number of table deletes  : 0
Number of table drops    : 0
Number of table age-outs : 0

Port          Neighbor Device ID       Neighbor Port ID    TTL
---------- ------------------------ ---------------------- ---
Et1           vios                     Gi0/0               120

veos>

```
