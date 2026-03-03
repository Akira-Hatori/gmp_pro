
% This function release the network resource and close library.
% usage:
% release_udp_helper();
function release_udp_helper()

% check if library is uninstalled or not installed
lib_path = which('MEX_UDP_Helper');
if(isempty(lib_path))
	disp('Cannot find UDP library.');
	return;
end

% release network resource
MEX_UDP_Helper("release_network");

% close library
clear MEX_UDP_Helper

end

