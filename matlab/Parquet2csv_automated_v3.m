function Parquet2csv_automated_v3(input_dir, TimeZone, StrTimeZone, pow_th, CBW, output_dir, T_inter)
    % Display inputs for confirmation
    fprintf('Input Dir: %s\nTZ: %s\nThresh: %d dBm\nCBW: %d Hz\n', input_dir, TimeZone, pow_th, CBW);

    myFiles = dir(fullfile(input_dir, '*.parquet'));
    if isempty(myFiles)
        error('No parquet files found in the specified directory.');
    end

    occupancyDir = fullfile(output_dir, 'channel occupancy');
    legendDir = fullfile(output_dir, 'frequency legends');
    if ~exist(occupancyDir, 'dir'), mkdir(occupancyDir); end
    if ~exist(legendDir, 'dir'), mkdir(legendDir); end

    % --- Parse File Timing ---
    fileDates = datetime({myFiles.date});
    Trace_time_start = dateshift(min(fileDates), 'start', 'hour');
    Trace_time_end = dateshift(max(fileDates) + seconds(1), 'start', 'hour');
    Duration = hours(Trace_time_end - Trace_time_start);
    
    Hour_bins = cell(Duration, 1);
    for IdxHour = 1:Duration
        windowStart = Trace_time_start + hours(IdxHour-1);
        windowEnd = Trace_time_start + hours(IdxHour);
        Hour_bins{IdxHour} = find(fileDates > windowStart & fileDates <= windowEnd);
    end

    % --- Process Data ---
    for IdxPwrThrd = 1:length(pow_th)
        curr_pow = pow_th(IdxPwrThrd);
        
        for IdxHour = 1:Duration
            if isempty(Hour_bins{IdxHour}), continue; end
            
            data_total = [];
            time_total = [];
            
            idxList = Hour_bins{IdxHour};
            for fIdx = 1:length(idxList)
                fname = fullfile(input_dir, myFiles(idxList(fIdx)).name);
                try
                    T = parquetread(fname);
                    time_total = [time_total; T.timestamp];
                    T_filt = T(T.trace_max >= curr_pow, :);
                    data_total = [data_total; T_filt.timestamp, T_filt.freqs];
                catch
                    continue
                end
            end

            if ~isempty(data_total)
                unique_times = unique(time_total);
                N_denominator = min(length(unique_times), 3600);

                [COoT, AUperHour, TS_start, bin_t_CO] = StatisticsPerHour_v3(data_total(:,1), data_total(:,2), CBW, T_inter, N_denominator);

                % Frequency Header Logic
                f_min = floor(min(data_total(:,2)) / CBW) * CBW; 
                f_max = ceil(max(data_total(:,2)) / CBW) * CBW;
                bin_f = f_min:CBW:f_max;
                
                % Create Frequency Legend (Start Freq, End Freq, Column Index)
                legendData = [(1:length(AUperHour))', bin_f(1:end-1)', bin_f(2:end)'];
                
                % Time Conversion
                utcTime = datetime(TS_start, 'ConvertFrom', 'posixtime', 'TimeZone', 'UTC');
                localTime = utcTime; localTime.TimeZone = TimeZone;
                dateHeader = [year(localTime), month(localTime), day(localTime), hour(localTime)];
                numChans = length(AUperHour);

                % --- Final Matrix Assembly ---
                Stat_AU = [dateHeader, TS_start, AUperHour, length(unique_times)];
                nCol = length(Stat_AU);  % 6 + numChans; same cols for AU and CO
                Stat_CO = zeros(60, nCol);
                Stat_CO(:, 1:4) = repmat(dateHeader, 60, 1);
                Stat_CO(:, 5) = repmat(TS_start, 60, 1);
                Stat_CO(:, 6) = bin_t_CO(1:60)';
                Stat_CO(:, 7:nCol) = COoT(1:60, :);

                Stat_Final = [Stat_AU; Stat_CO];

                % --- Save Files ---
                Timestr = datestr(localTime, 'yyyy_mm_dd_HH');
                
                % Data File
                fname_out = fullfile(occupancyDir, sprintf('Data_%s_%ddBm.csv', Timestr, abs(curr_pow)));
                writematrix(Stat_Final, fname_out);
                
                % Legend File (Frequency Mapping)
                fname_leg = fullfile(legendDir, sprintf('Legend_%s.csv', Timestr));
                writematrix(legendData, fname_leg);
            end
        end
    end
    disp('Processing Complete. Check "channel occupancy" and "frequency legends" folders.');
end