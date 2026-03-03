
% This function should be called when Simulink Communication Module is invoked.

% usage example:
% sl_udp_server_init_cb("127.0.0.1", [12300, 12301, 12302, 12303])

function sl_udp_server_init_cb(ip_addr, ports)

% register external function 
coder.extrinsic('MEX_UDP_Helper');

% bug fix: pre-release network to avoid socket abuse.
MEX_UDP_Helper("release_network");

% load library
MEX_UDP_Helper("Hello");

% Register Connection Target and connection ports
%MEX_UDP_Helper("config_network", "127.0.0.1", 12300, 12301, 12302, 12303);
MEX_UDP_Helper("config_network", ip_addr, ports(1), ports(2), ports(3), ports(4));

% Create Connection
MEX_UDP_Helper("link_network");

% Send Simulation Start Command
MEX_UDP_Helper("send_cmd", int8(['start']));

end
