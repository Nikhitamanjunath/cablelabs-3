function [COoT, AUperHour, Timestamp_start, bin_t_CO] = StatisticsPerHour_v3(Timestamp, Freq, CBW, T_inter, N_denominator)
    % 1. Dynamically define frequency bins based on the input data range
    f_min = floor(min(Freq) / CBW) * CBW; 
    f_max = ceil(max(Freq) / CBW) * CBW;
    bin_f = f_min:CBW:f_max;

    % 2. Define time bins
    Timestamp_start = Timestamp(1) - mod(Timestamp(1), 3600);
    bin_t_AU = Timestamp_start:1:Timestamp_start+3600; 
    bin_t_CO = Timestamp_start:T_inter:Timestamp_start+3600;

    % 3. Process Airtime Utilization (AU)
    inRange = Freq >= bin_f(1) & Freq < bin_f(end) ...
           & Timestamp >= bin_t_AU(1) & Timestamp < bin_t_AU(end);
    
    if any(inRange)
        ccAUoT = histcounts2(Timestamp(inRange), Freq(inRange), bin_t_AU, bin_f);
        AUoT = ccAUoT > 0;
        AUperHour = sum(AUoT, 1) / N_denominator * 100;

        % 4. Process Channel Occupancy (CO)
        ccAUoT_CO = histcounts2(Timestamp(inRange), Freq(inRange), bin_t_CO, bin_f); 
        COoT = ccAUoT_CO > 0;
    else
        % Return empty/zero structures if no data fits the range
        AUperHour = zeros(1, length(bin_f)-1);
        COoT = zeros(length(bin_t_CO)-1, length(bin_f)-1);
    end
end