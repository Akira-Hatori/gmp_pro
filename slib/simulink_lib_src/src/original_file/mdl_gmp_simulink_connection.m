

% Test Command
% [HostAddr, TargetPort] = mdl_gmp_simulink_connection("127.0.0.1", 12300, 12301, 12302, 12303)


% HostAddr =
%    127     0     0     1


% TargetPort =
%        12300       12301       12302       12303

function [HostAddr, TargetPort] = mdl_gmp_simulink_connection(MaskHostAddr, ...
    MaskMsgTxPort, MaskMsgRxPort, ...
    MaskCmdTxPort, MaskCmdRxPort)

% validate IP address
IP_REGEX = "(((\d)|([1-9]\d)|(1\d{2})|(2[0-4]\d)|(25[0-5]))\.){3}((\d)|([1-9]\d)|(1\d{2})|(2[0-4]\d)|(25[0-5]))";
ret = regexp(MaskHostAddr, IP_REGEX);
if (isempty(ret) || ret ~= 1)
    error("Hast Address must be a plain IP address");
end

splitAddr = split(MaskHostAddr,".");
HostAddr = str2double(splitAddr)';

TargetPort = [MaskMsgTxPort, MaskMsgRxPort, MaskCmdTxPort, MaskCmdRxPort];

end
