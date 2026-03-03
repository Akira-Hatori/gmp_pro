function msg = udp_recv(length)

coder.extrinsic('MEX_UDP_Helper');

%codegen MEX_UDP_Helper -args {coder.typeof('c', [1 Inf])} -report
msg = MEX_UDP_Helper("recv_msg", length);

end