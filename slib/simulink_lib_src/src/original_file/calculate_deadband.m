
% This file will calculate deadband time in us.

function calculate_deadband(blockHandle, ...
	dead_band_upper_edit_box_name, dead_band_lower_edit_box_name, ...
	compare_max_name, switch_freq_name, dead_band_us_name)

% Get handle of Mask
mask_obj = Simulink.Mask.get(blockHandle);
Parameters = Simulink.Mask.get(blockHandle).Parameters;

% Get source data
dead_band_up = str2double(Parameters(strcmp(get_param(blockHandle,'MaskNames'), dead_band_upper_edit_box_name)==1).Value);
dead_band_dn = str2double(Parameters(strcmp(get_param(blockHandle,'MaskNames'), dead_band_lower_edit_box_name)==1).Value);
cmp_max = str2double(Parameters(strcmp(get_param(blockHandle,'MaskNames'), compare_max_name)==1).Value);
switch_freq = str2double(Parameters(strcmp(get_param(blockHandle,'MaskNames'), switch_freq_name)==1).Value);

% calculate deadband
dead_band_us = 1/switch_freq * (dead_band_up + dead_band_dn) / cmp_max*1e6 /2;

% Set result
Parameters(strcmp(get_param(blockHandle,'MaskNames'),dead_band_us_name)==1).Value=num2str(dead_band_us);

end
