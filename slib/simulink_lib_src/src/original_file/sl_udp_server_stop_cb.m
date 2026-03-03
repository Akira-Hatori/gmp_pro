
% This functoin should be called when a Simulink model is complete and stop.

% usage example:
% sl_udp_server_stop_cb()

function sl_udp_server_stop_cb()

% send complete command
MEX_UDP_Helper("send_cmd", int8(['stop']));

% release network resource
MEX_UDP_Helper("release_network");

end
